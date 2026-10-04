import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import random
import time

import numpy as np
import torch

from interface.common import timed, timed_often
from .experiment import restore
from .job import record as save_json
from .metrics import accuracy, combined, differentiation, scale_targets, utility
from .model import Configuration, Network, collate
from .removals import ATTEMPTS
from .schema import GRAPH_VERSION
from .tracking import FitTracker, RunTracker
from .world_data import read, validate_dataset


@timed_often
def case(packed,row):
    return read(packed/f'{row["run"]}_{row["seq"]}.pkl')


def stream(packed,rows):
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending=[]
        for row in rows:
            pending.append(pool.submit(case,packed,row))
            if len(pending)==3:
                yield pending.pop(0).result()
        for future in pending:
            yield future.result()


@timed
def sequences(manifest,rows):
    wanted={(row['run'],row['seq']) for row in rows}
    runs={row['run'] for row in rows}
    frames=[row for row in manifest['frames'] if row['run'] in runs]
    if {(row['run'],row['seq']) for row in frames if row['decision']}!=wanted:
        raise ValueError('Recurrent processing requires every decision in each selected run')
    return [[row for row in sorted(frames,key=lambda row:row['seq']) if row['run']==run] for run in sorted(runs)]


@timed
def forecasts(model,packed,rows,name,mean,scale,progress=None,with_alternatives=False):
    if name!='full_world':
        raise ValueError('Recurrent fitting uses the complete world')
    manifest=json.loads((packed/'dataset.json').read_text())
    predictions=[]
    records=[]
    candidates=[]
    identifiers=[]
    device=next(model.parameters()).device
    model.eval()
    with torch.inference_mode():
        for group in sequences(manifest,rows):
            memory=None
            for frame in stream(packed,group):
                record=frame['record']
                observation=model.observe(collate([frame['graph']],device),memory,record['hour'])
                if not record['decision']:
                    memory=observation.memory
                    continue
                proposed=model.propose(observation,frame['proposal'])
                predictions.append(proposed.prediction.cpu().numpy()[0]*scale+mean)
                records.append(record)
                if with_alternatives:
                    if not frame['deltas']:
                        raise ValueError('Every held-out decision requires candidate alternatives')
                    candidates.append(np.stack([model.propose(observation,delta).prediction.cpu().numpy()[0]*scale+mean for delta in frame['deltas']]))
                    identifiers.append([record['run'],record['seq']])
                memory=model.commit(observation,proposed)
                if progress:
                    progress.advance(len(records),len(rows))
    return np.stack(predictions),records,candidates,identifiers


@timed
def train_epoch(model,optimizer,packed,groups,mean,scale,progress):
    device=next(model.parameters()).device
    model.train()
    total=sum(row['decision'] for group in groups for row in group)
    done=0
    loss_sum=0.
    observations=0
    for group in groups:
        memory=None
        losses=[]
        observed=0
        optimizer.zero_grad(set_to_none=True)
        for position,frame in enumerate(stream(packed,group)):
            record=frame['record']
            observation=model.observe(collate([frame['graph']],device),memory,record['hour'])
            memory=observation.memory
            if record['decision']:
                proposed=model.propose(observation,frame['proposal'])
                target=torch.as_tensor((record['y']-mean)/scale,dtype=torch.float32,device=device)
                visible=torch.as_tensor(record['mask'],dtype=torch.float32,device=device)
                loss=((proposed.prediction[0]-target).square()*visible).sum()
                if not torch.isfinite(loss):
                    raise ValueError('Nonfinite recurrent training loss')
                losses.append(loss)
                observed+=int(record['mask'].sum())
                loss_sum+=float(loss.detach())
                memory=model.commit(observation,proposed)
                done+=1
                if progress:
                    progress.advance(done,total)
            if (position+1)%model.configuration.sequence_length==0 or position+1==len(group):
                if observed:
                    (sum(losses)/observed).backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(),5.,error_if_nonfinite=True)
                    optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                memory=memory.detach()
                observations+=observed
                losses=[]
                observed=0
    return loss_sum/max(observations,1)


@timed_often
def labels(records):
    return np.stack([r['y'] for r in records]),np.stack([r['mask'] for r in records])


@timed
def evaluate(model,checkpoint,packed,output,rows,name,split,progress=None):
    mean,scale=np.array(checkpoint['mean']),np.array(checkpoint['scale'])
    if progress:
        progress.update(phase=split,done=0,total=len(rows))
    prediction,records,candidates,pauses=forecasts(model,packed,rows,name,mean,scale,progress,with_alternatives=True)
    y,mask=labels(records)
    scores=combined(accuracy(prediction,y,mask,scale,checkpoint['reward_scale']),differentiation(candidates,checkpoint['reward_scale']))
    np.savez_compressed(output/f'{split}.npz',prediction=prediction,target=y,mask=mask,
                        run=np.array([r['run'] for r in records]),seq=np.array([r['seq'] for r in records]),
                        baseline=np.stack([r['baseline'] for r in records]),candidates=np.stack(candidates),candidate_pauses=np.array(pauses))
    print(json.dumps({'stage':split,'name':name,'scores':scores}),flush=True)
    return scores


@timed
def fit(packed,output,name,configuration,manifest):
    progress=FitTracker(output,name,configuration)
    try:
        result=fit_model(packed,output,name,configuration,manifest,progress)
        progress.update(state='complete',phase='fitted',seconds=result['seconds'],best_epoch=result['best_epoch'])
        return result
    except BaseException as error:
        progress.update(state='failed',phase='fit',error=str(error) or type(error).__name__)
        raise


@timed
def fit_model(packed,output,name,configuration,manifest,progress):
    validate_dataset(manifest)
    if name!='full_world':
        raise ValueError('Recurrent fitting uses the complete world')
    output.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    train=[r for r in manifest['rows'] if r['split']=='train']
    validation=[r for r in manifest['rows'] if r['split']=='validation']
    records=[read(packed/f'{r["run"]}_{r["seq"]}.pkl',materialize=False)['record'] for r in train]
    y,mask=labels(records)
    mean,scale=scale_targets(y,mask)
    reward_scale=float(np.std(utility(y[mask.all(axis=(1,2))])))
    if not np.isfinite(reward_scale) or reward_scale<=0:
        raise ValueError('Training reward variation is required')
    random.seed(configuration.seed)
    np.random.seed(configuration.seed)
    torch.manual_seed(configuration.seed)
    torch.cuda.manual_seed_all(configuration.seed)
    model=Network(manifest['tokens'],len(manifest['node_types'])+1,len(manifest['relations'])+1,configuration).cuda()
    optimizer=torch.optim.AdamW(model.parameters(),lr=configuration.learning_rate,weight_decay=configuration.weight_decay)
    best=float('inf')
    best_epoch=0
    log=[]
    rng=np.random.default_rng(configuration.seed)
    groups=sequences(manifest,train)
    torch.cuda.reset_peak_memory_stats()
    for epoch in range(configuration.epochs):
        tick=time.monotonic()
        progress.update(phase='training',epoch=epoch+1,done=0,total=len(train))
        order=[groups[index] for index in rng.permutation(len(groups))]
        training_mse=train_epoch(model,optimizer,packed,order,mean,scale,progress)
        progress.update(phase='validation',done=0,total=len(validation))
        prediction,held,_,_=forecasts(model,packed,validation,name,mean,scale,progress)
        actual,present=labels(held)
        scores=accuracy(prediction,actual,present,scale,reward_scale)
        value=scores['sequence_nrmse']
        entry={'epoch':epoch+1,'training_mse':training_mse,'validation_sequence_nrmse':value,'seconds':time.monotonic()-tick}
        log.append(entry)
        save_json(output/'progress.json',log)
        print(json.dumps({'name':name,**entry}),flush=True)
        if value<best:
            best,best_epoch=value,epoch+1
            torch.save({'graph_version':GRAPH_VERSION,'state':model.state_dict(),'configuration':configuration.mapping(),
                        'tokens':manifest['tokens'],'kinds':len(manifest['node_types'])+1,'relations':len(manifest['relations'])+1,
                        'mean':mean.tolist(),'scale':scale.tolist(),'reward_scale':reward_scale,'design':name,
                        'source_sha256':manifest['source_sha256']},output/'model.pt')
        progress.update(best_epoch=best_epoch,training_mse=entry['training_mse'],validation_sequence_nrmse=value,
                        gpu_peak_bytes=torch.cuda.max_memory_allocated())
        if epoch+1-best_epoch>=configuration.patience:
            break
    peak=torch.cuda.max_memory_allocated()
    del model,optimizer
    model,checkpoint=restore(output/'model.pt')
    scores=evaluate(model,checkpoint,packed,output,validation,name,'validation',progress)
    result={'graph_version':GRAPH_VERSION,'name':name,'design':name,'removed_components':ATTEMPTS[name],'configuration':configuration.mapping(),
            'sequence_length':configuration.sequence_length,'parameters':sum(p.numel() for p in model.parameters()),'epochs':log,
            'epochs_run':len(log),'best_epoch':best_epoch,'validation':scores,'training_rows':len(train),
            'validation_rows':len(validation),'seconds':time.monotonic()-started,'gpu_peak_bytes':peak,'reward_scale':reward_scale}
    save_json(output/'result.json',result)
    return result


@timed
def run(packed,output,epochs,workers=1,attempts=('full_world',),wait_for=None):
    tracker=RunTracker(output,packed,Configuration(epochs=epochs),attempts)
    try:
        if wait_for and not (packed/'complete.json').exists():
            tracker.update(phase='waiting_for_data')
            while not (packed/'complete.json').exists():
                if json.loads(wait_for.read_text())['state']=='failed':
                    raise RuntimeError('World preparation failed')
                time.sleep(5)
        experiment(packed,output,epochs,workers,attempts,tracker)
        tracker.update(state='complete',phase='complete')
    except BaseException as error:
        tracker.update(state='failed',error=str(error) or type(error).__name__)
        raise


@timed
def experiment(packed,output,epochs,workers,attempts,tracker):
    if tuple(attempts)!=('full_world',):
        raise ValueError('Recurrent experiments use the complete world; tune its network with world_tune')
    if not (packed/'complete.json').exists():
        raise ValueError('World preparation is incomplete')
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32=False
    output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((packed/'dataset.json').read_text())
    if manifest.get('graph_version')!=GRAPH_VERSION:
        raise ValueError('Dataset is obsolete; rebuild recurrent frames before fitting')
    validate_dataset(manifest)
    for path in output.glob('*/result.json'):
        if json.loads(path.read_text()).get('graph_version')!=GRAPH_VERSION:
            raise ValueError('Saved fit is obsolete; use a new output directory')
    configuration=Configuration(epochs=epochs)
    tracker.update(phase='fitting')
    results=[]
    for name in ('full_world',):
        path=output/name/'result.json'
        result=json.loads(path.read_text()) if path.exists() else fit(packed,output/name,name,configuration,manifest)
        results.append(result)
        save_json(output/'results.json',results)
        tracker.update(completed_fits=len(results))
        torch.cuda.empty_cache()
    selection={'baseline':'full_world','selected':min(results,key=lambda r:r['validation']['score'])['name'],
               'criterion':'.1 normalized reward RMSE + .9 (1 - candidate entropy)',
               'epoch_selection':'validation normalized sequence RMSE','test_not_used_for_selection':True,
               'precision':'float32; TF32 disabled','torch_version':torch.__version__,'device':torch.cuda.get_device_name(0),
               'sequence_length':configuration.sequence_length}
    save_json(output/'selection.json',selection)
    tracker.update(phase='test',completed_fits=len(results),selected=selection['selected'])
    held=[r for r in manifest['rows'] if r['split']=='test']
    for result in results:
        if 'test' not in result:
            tracker.update(evaluating=result['name'])
            model,checkpoint=restore(output/result['name']/'model.pt')
            result['test']=evaluate(model,checkpoint,packed,output/result['name'],held,result['name'],'test')
            save_json(output/result['name']/'result.json',result)
            del model
            torch.cuda.empty_cache()
        save_json(output/'results.json',results)


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--packed',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--epochs',type=int,default=24)
    parser.add_argument('--wait-for',type=Path)
    parser.add_argument('--workers',type=int,choices=(1,2),default=1)
    parser.add_argument('--attempts',nargs='+',choices=('full_world',),default=['full_world'])
    args=parser.parse_args()
    run(args.packed,args.output,args.epochs,args.workers,args.attempts,args.wait_for)


if __name__=='__main__':
    main()
