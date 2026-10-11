import argparse
from collections import Counter
import gzip
import json
from pathlib import Path

from interface.common import evidence, timed
from interface.recording.spec import ENTITIES
from .graph import audit
from .removals import ATTEMPTS, DESCRIPTIONS, derive
from .report import graph_report
from .schema import FULL_WORLD
from .source import load
from .world import build_world


@timed
def catalog(root,data,actions,names=('full_world',)):
    directory=root/'graphs'
    directory.mkdir(parents=True,exist_ok=True)
    base,full_audit=build_world(data,actions)
    examples=[]
    designs=[]
    original=Counter(n['kind'] for n in base.nodes if n['kind'] in ENTITIES)
    for name in names:
        removed=ATTEMPTS[name]
        graph=derive(base,data,name)
        counts=Counter(n['kind'] for n in graph.nodes if n['kind'] in ENTITIES)
        if counts!=original:
            raise ValueError(evidence(counts=counts,original=original))
        summary=full_audit if name=='full_world' else audit(graph,data['dates'][data['seq']])
        summary={**summary,'nodes':len(graph.nodes),'edges':len(graph.edges),'removed_nodes':len(base.nodes)-len(graph.nodes),
                 'removed_edges':len(base.edges)-len(graph.edges),
                 'removed_attributes':sum(len(n['attrs']) for n in base.nodes)-sum(len(n['attrs']) for n in graph.nodes),
                 'core_entities':dict(counts),'all_core_entities_preserved':True}
        parameters={**FULL_WORLD.mapping(),'name':name,'removed_components':removed}
        example={'design':parameters,'run':data['run'],'seq':data['seq'],'nodes':graph.nodes,'edges':graph.edges,
                 'player':graph.player,'block':graph.block,'audit':summary}
        with gzip.open(directory/(name+'.json.gz'),'wt',encoding='utf-8',compresslevel=1) as stream:
            json.dump(example,stream)
        examples.append(example)
        designs.append({'parameters':parameters,'description':DESCRIPTIONS[name],'snapshots':[summary]})
        print(json.dumps({'name':name,'nodes':len(graph.nodes),'edges':len(graph.edges),'removed_attributes':summary['removed_attributes']}),flush=True)
    result={'baseline':'full_world','designs':designs,'run':data['run'],'seq':data['seq']}
    graph_report({**result,'examples':examples},directory/'graphs.html')
    (directory/'audit.json').write_text(json.dumps(result,indent=2))
    (root/'full_world/audit.json').write_text(json.dumps(full_audit,indent=2))


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    data=load(args.root/'full_world/source.pkl.gz')
    blocks=json.loads((args.root/'full_world/candidates.json').read_text())['blocks']
    catalog(args.root,data,blocks[0])


if __name__=='__main__':
    main()
