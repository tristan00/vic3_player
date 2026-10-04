import argparse
from concurrent.futures import ProcessPoolExecutor
import gc
import hashlib
import json
from pathlib import Path
import pickle
import time

import numpy as np
import psycopg

from interface.common import timed, timed_often
from interface.options.stored import Shared
from interface.recording.store import DSN
from .encoding import Encoder, Survey, fragment
from .graph import Graph
from .schema import GRAPH_VERSION
from .replay import ReplayReader, ReplaySnapshot
from .source import candidates, load, save
from .world import WORLD_TABLES, WorldBuilder, build_world


@timed_often
def write(path,value):
    temporary=path.with_suffix('.tmp')
    with temporary.open('wb') as stream:
        pickle.dump(value,stream,pickle.HIGHEST_PROTOCOL)
    temporary.replace(path)


@timed_often
def read(path,materialize=True):
    with (path if materialize else path.with_suffix('.record.pkl')).open('rb') as stream:
        value=pickle.load(stream)
    if value.get('graph_version')!=GRAPH_VERSION:
        raise ValueError('Graph storage is obsolete; rebuild recurrent frames')
    return value


class Identities:
    @timed_often
    def __init__(self):
        self.indices={}

    @timed
    def graph(self,graph):
        return np.asarray([self.indices.setdefault((node['kind'],node['key']),len(self.indices))
                           for node in graph.nodes],np.int64)


@timed
def validate_dataset(manifest):
    rows=manifest['rows']
    if manifest.get('graph_version')!=GRAPH_VERSION or manifest.get('storage')!='recurrent_frames':
        raise ValueError('Dataset must use recurrent frames; rebuild obsolete graphs')
    if manifest.get('coverage')!='all_recorded_decisions' or manifest.get('total_recorded_pauses')!=len(rows):
        raise ValueError('Dataset must contain every recorded decision; rebuild without sampling')
    if len({(row['run'],row['seq']) for row in rows})!=len(rows):
        raise ValueError('Dataset contains duplicate decisions')
    frames=manifest.get('frames',[])
    if len({(row['run'],row['seq']) for row in frames})!=len(frames):
        raise ValueError('Dataset contains duplicate observations')
    decisions={(row['run'],row['seq'],row['split']) for row in rows}
    if {(row['run'],row['seq'],row['split']) for row in frames if row['decision']}!=decisions:
        raise ValueError('Recurrent frames must include every decision in its assigned split')
    splits={}
    for row in frames:
        if splits.setdefault(row['run'],row['split'])!=row['split']:
            raise ValueError('All observations in a run must belong to the same split')


@timed
def action_graph(base,data,actions,context=None):
    end=base.block if base.nodes[base.block]['kind']=='action_block' else len(base.nodes)
    builder=WorldBuilder(data) if context is None else context
    if context is None:
        builder.nodes=list(base.nodes[:end])
        builder.lookup={(n['seq'],n['kind'],n['key']):i for i,n in enumerate(builder.nodes)}
    else:
        for node in builder.nodes[end:]:
            del builder.lookup[node['seq'],node['kind'],node['key']]
        del builder.nodes[end:]
        builder.edges=[]
        builder.audit.clear()
        builder.audit['graph_version']=GRAPH_VERSION
    block=builder.candidate(actions,data['seq'],data['dates'][data['seq']],data['player'])
    return Graph(builder.nodes[end:],builder.edges,base.player,block-end,dict(builder.audit))


@timed
def join(base,delta):
    end=base['world_nodes']
    stop=base['offsets'][end]
    result={key:np.concatenate((base[key][:end],delta[key])) for key in ('kind','current','action','remove_nodes') if key in base and key in delta}
    result.update({key:np.concatenate((base[key][:stop],delta[key])) for key in ('tokens','values','remove_tokens') if key in base and key in delta})
    edge_keep=(base['edge_index']<end).all(axis=0)
    result.update({key:np.concatenate((base[key][edge_keep],delta[key])) for key in ('relation','weight')})
    result.update(edge_index=np.concatenate((base['edge_index'][:,edge_keep],delta['edge_index']),axis=1),
                  offsets=np.r_[base['offsets'][:end],delta['offsets']+stop].astype(np.int32),
                  identity=np.r_[base['identity'][:end],np.arange(end,end+delta['nodes'])],world_nodes=end,
                  player=base['player'],block=end+delta['block'],nodes=end+delta['nodes'],audit=delta['audit'])
    return result


@timed
def encode_fragment(graph,data):
    return fragment(graph)


@timed
def extract_run(arguments):
    collecting=gc.isenabled()
    gc.disable()
    try:
        return extract_frames(arguments)
    finally:
        if collecting:
            gc.enable()
        gc.collect()


@timed
def extract_frames(arguments):
    source,output,run=arguments
    tasks=load(source/f'run_{run}.pkl.gz')['tasks']
    chosen={task['seq']:task for task in tasks}
    rows=[]
    frames=[]
    identities=Identities()
    with psycopg.connect(DSN) as connection:
        connection.execute('set transaction isolation level repeatable read read only')
        reader=ReplayReader(connection,run,max(chosen))
        shared=Shared(connection) if tasks[0]['split']!='train' else None
        if shared is not None:
            shared.names.update(reader.vocabulary)
        if len(tasks)!=len(chosen) or sorted(chosen)!=sorted(reader.actions):
            raise ValueError(f'Source must contain every recorded decision for run {run}')
        if len({task['split'] for task in tasks})!=1:
            raise ValueError('A run cannot cross dataset splits')
        for seq in sorted(at for at in reader.dates if at<=max(chosen)):
            started=time.monotonic()
            data=reader.read(seq)
            graph,audit=build_world(data)
            encoded,mapping=encode_fragment(graph,data)
            encoded['graph']['identity']=identities.graph(graph)
            survey=Survey()
            survey.merge(mapping)
            task=chosen.get(seq)
            record={'run':run,'seq':seq,'hour':reader.dates[seq],'split':tasks[0]['split'],
                    'actions':None,'decision':task is not None}
            if task is not None:
                record.update(task,history=[seq])
            proposal=None
            drawn=[]
            deltas=[]
            if task is not None:
                context=WorldBuilder(data)
                context.nodes=list(graph.nodes)
                context.lookup={(n['seq'],n['kind'],n['key']):i for i,n in enumerate(context.nodes)}
                proposal,mapping=encode_fragment(action_graph(graph,data,task['actions'],context),data)
                survey.merge(mapping)
                if task['split']!='train':
                    snapshot=ReplaySnapshot(connection,data,shared)
                    drawn=candidates(connection,run,seq,30,20261001+run*1009+seq,snapshot=snapshot)
                    for actions in drawn:
                        packed,mapping=encode_fragment(action_graph(graph,data,actions,context),data)
                        deltas.append(packed)
            path=output/f'{run}_{seq}.raw'
            write(path,{'graph_version':GRAPH_VERSION,'graph':encoded,'record':record,
                        'proposal':proposal,'deltas':deltas,'actions':drawn})
            write(path.with_suffix('.record.pkl'),{'graph_version':GRAPH_VERSION,'record':record})
            if record['split']=='train':
                save(path.with_suffix('.survey.gz'),survey.mapping())
            summary={'graph_version':GRAPH_VERSION,'run':run,'seq':seq,'hour':record['hour'],'split':record['split'],
                     'decision':task is not None,'nodes':len(graph.nodes),'edges':len(graph.edges),'entropy':bool(drawn),
                     'source_rows':sum(r['source_rows'] for r in audit['coverage']),
                     'missing_entities':len(audit['missing_entity_records']),'seconds':time.monotonic()-started}
            frames.append(summary)
            if task is not None:
                rows.append(summary)
            print(json.dumps(summary),flush=True)
    return {'rows':rows,'frames':frames}


@timed
def remap(packed,local,encoder):
    ids=np.zeros(len(local.tokens),np.int32)
    means=np.zeros(len(local.tokens),packed['values'].dtype)
    scales=np.ones(len(local.tokens),packed['values'].dtype)
    numeric=np.zeros(len(local.tokens),bool)
    available=np.ones(len(local.tokens),bool)
    for key,index in local.tokens.items():
        ids[index]=encoder.tokens.get(key,encoder.tokens.get(('unknown',key[1]),0))
        if key[0] in ('number','present') and key[1] not in encoder.stats:
            available[index]=False
        if key[0]=='number':
            numeric[index]=True
            if key[1] in encoder.stats:
                means[index],scales[index]=encoder.stats[key[1]]
    original=packed['tokens']
    selected=numeric[original]
    packed['values'][selected]=np.clip((packed['values'][selected]-means[original[selected]])/scales[original[selected]],-8,8)
    packed['values']=packed['values'].astype(np.float32)
    packed['tokens']=ids[original]
    keep=available[original]
    cumulative=np.r_[0,np.cumsum(keep)]
    packed['offsets']=cumulative[packed['offsets']].astype(np.int32)
    for key in ('tokens','values','remove_tokens'):
        if key in packed:
            packed[key]=packed[key][keep]
    kind=np.zeros(len(local.kinds)+1,np.int16)
    relation=np.zeros(len(local.relations)+1,np.int16)
    for key,index in local.kinds.items():
        kind[index]=encoder.kinds.get(key,0)
    for key,index in local.relations.items():
        relation[index]=encoder.relations.get(key,0)
    packed['kind']=kind[packed['kind']]
    packed['relation']=relation[packed['relation']]
    return packed


@timed
def pack_run(arguments):
    output,run=arguments
    encoder=load(output/'encoder.pkl.gz')
    for path in sorted(output.glob(f'{run}_*.raw')):
        with path.open('rb') as stream:
            found=pickle.load(stream)
        for key in ('graph','proposal'):
            if found[key] is not None:
                found[key]=remap(found[key]['graph'],found[key]['encoder'],encoder)
        found['deltas']=[remap(delta['graph'],delta['encoder'],encoder) for delta in found['deltas']]
        if any(not np.isfinite(graph['values']).all() for graph in (found['graph'],found['proposal'],*found['deltas']) if graph is not None):
            raise ValueError(f'Nonfinite world features in {path}')
        write(path.with_suffix('.pkl'),found)
        path.unlink()


@timed
def prepare(source,output,workers):
    manifest=json.loads((source/'dataset.json').read_text())
    if manifest.get('coverage')!='all_recorded_decisions' or len(manifest['tasks'])!=manifest['total_recorded_pauses']:
        raise ValueError('Source must contain every recorded decision; export it again without sampling')
    output.mkdir(parents=True,exist_ok=False)
    runs=sorted({t['run'] for t in manifest['tasks']})
    started=time.monotonic()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        partitions=list(pool.map(extract_run,[(source,output,r) for r in runs]))
    rows=[row for partition in partitions for row in partition['rows']]
    frames=[row for partition in partitions for row in partition['frames']]
    expected={(t['run'],t['seq']) for t in manifest['tasks']}
    observed={(r['run'],r['seq']) for r in rows}
    if expected!=observed or len(rows)!=len(manifest['tasks']):
        raise ValueError('Graph creation must cover every source decision exactly once')
    encoder=Encoder(load(output/f'{row["run"]}_{row["seq"]}.survey.gz') for row in frames if row['split']=='train')
    save(output/'encoder.pkl.gz',encoder)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        list(pool.map(pack_run,[(output,run) for run in runs]))
    result={'graph_version':GRAPH_VERSION,'storage':'recurrent_frames','coverage':'all_recorded_decisions',
            'total_recorded_pauses':len(rows),'rows':rows,'frames':frames,'source_sha256':hashlib.sha256((source/'dataset.json').read_bytes()).hexdigest(),
            'designs':{'full_world':[]},'tokens':len(encoder.tokens),'node_types':encoder.kinds,
            'relations':encoder.relations,'source':str(source.resolve()),
            'feature_tables':WORLD_TABLES,'feature_reader':'replay.ReplayReader',
            'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')},
            'seconds':time.monotonic()-started}
    validate_dataset(result)
    (output/'dataset.json').write_text(json.dumps(result,indent=2))
    (output/'complete.json').write_text(json.dumps({'cases':len(rows),'seconds':time.monotonic()-started}))


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=8)
    args=parser.parse_args()
    prepare(args.source,args.output,args.workers)


if __name__=='__main__':
    main()
