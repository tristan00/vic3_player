import argparse
from dataclasses import replace
import gc
import json
from pathlib import Path
import time

import numpy as np
import torch

from interface.common import evidence, timed
from .experiment import restore
from .job import record
from .model import Configuration
from .schema import GRAPH_VERSION
from .tracking import RunTracker
from .world_data import validate_dataset
from .world_experiment import evaluate, fit


@timed
def configurations(count,epochs):
    if not 1<=count<=12:
        raise ValueError(evidence(count=count))
    baseline=Configuration(epochs=epochs)
    found={'full_world':baseline}
    rng=np.random.default_rng(20261001)
    shapes=[(operator,width,layers) for operator in ('relational_mean','relational_attention')
            for width in (32,48,64) for layers in (2,3,4)]
    shapes=[shape for shape in shapes if shape!=('relational_mean',48,3)]
    rng.shuffle(shapes)
    for index,(operator,width,layers) in enumerate(shapes[:count-1],1):
        found[f'trial_{index:03}']=replace(baseline,operator=operator,width=width,layers=layers,
            dropout=float(rng.choice([0.,.1,.2,.35])),
            learning_rate=float(np.exp(rng.uniform(np.log(.0001),np.log(.003)))),
            weight_decay=0. if index%4==0 else float(np.exp(rng.uniform(np.log(.000001),np.log(.01)))))
    return found


@timed
def search(packed,output,trials,epochs,wait_for):
    planned=configurations(trials,epochs)
    tracker=RunTracker(output,packed,planned['full_world'],tuple(planned))
    tracker.update(configurations={name:config.mapping() for name,config in planned.items()},
                   search_kind='initial_parameter_search',phase='waiting_for_data')
    try:
        while not (packed/'complete.json').exists():
            if wait_for is None:
                raise ValueError(evidence(wait_for=wait_for,path=packed/'complete.json'))
            status=json.loads(wait_for.read_text())
            if status['state']=='failed':
                raise RuntimeError(evidence(status=status))
            if status['state']=='complete':
                raise RuntimeError(evidence(status=status,path=packed/'complete.json'))
            time.sleep(5)
        manifest=json.loads((packed/'dataset.json').read_text())
        if manifest.get('graph_version')!=GRAPH_VERSION:
            raise ValueError(evidence(found=manifest.get('graph_version'),expected=GRAPH_VERSION))
        validate_dataset(manifest)
        plan={'graph_version':GRAPH_VERSION,'configurations':{name:config.mapping() for name,config in planned.items()},
              'source_sha256':manifest['source_sha256'],'packed':str(packed.resolve()),
              'criterion':'.1 normalized reward RMSE + .9 (1 - candidate entropy)',
              'epoch_selection':'validation normalized sequence RMSE','test_not_used_for_selection':True}
        if (output/'search.json').exists() and json.loads((output/'search.json').read_text())!=plan:
            raise ValueError(evidence(path=output/'search.json'))
        record(output/'search.json',plan)
        torch.set_num_threads(4)
        torch.backends.cuda.matmul.allow_tf32=False
        results=[]
        for name,config in planned.items():
            tracker.update(phase='fitting',evaluating=None)
            target=output/name
            if (target/'result.json').exists():
                result=json.loads((target/'result.json').read_text())
                if result.get('graph_version')!=GRAPH_VERSION or result['configuration']!=config.mapping():
                    raise ValueError(evidence(found=result.get('graph_version'),expected=GRAPH_VERSION,saved=result['configuration'],searched=config.mapping()))
            else:
                try:
                    result=fit(packed,target,'full_world',config,manifest)
                except torch.OutOfMemoryError:
                    gc.collect()
                    torch.cuda.empty_cache()
                    continue
                result['name']=name
                record(target/'result.json',result)
            results.append(result)
            record(output/'results.json',results)
            tracker.update(completed_fits=len(results),selected=min(results,key=lambda row:row['validation']['score'])['name'])
            gc.collect()
            torch.cuda.empty_cache()
        if not results:
            raise RuntimeError(evidence(results=results))
        selected=min(results,key=lambda row:row['validation']['score'])['name']
        record(output/'selection.json',{'baseline':'full_world','selected':selected,'criterion':plan['criterion'],
                                        'epoch_selection':plan['epoch_selection'],'test_not_used_for_selection':True})
        held=[row for row in manifest['rows'] if row['split']=='test']
        for result in results:
            if result['name'] not in ('full_world',selected):
                continue
            if 'test' not in result:
                tracker.update(phase='test',evaluating=result['name'])
                model,checkpoint=restore(output/result['name']/'model.pt')
                result['test']=evaluate(model,checkpoint,packed,output/result['name'],held,'full_world','test')
                record(output/result['name']/'result.json',result)
                del model
                gc.collect()
                torch.cuda.empty_cache()
            record(output/'results.json',results)
        tracker.update(state='complete',phase='complete',evaluating=None,selected=selected)
    except BaseException as error:
        tracker.update(state='failed',error=str(error) or type(error).__name__)
        raise


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--packed',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--trials',type=int,default=12)
    parser.add_argument('--epochs',type=int,default=24)
    parser.add_argument('--wait-for',type=Path)
    args=parser.parse_args()
    search(args.packed,args.output,args.trials,args.epochs,args.wait_for)


if __name__=='__main__':
    main()
