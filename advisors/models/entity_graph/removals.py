from collections import Counter

import numpy as np

from interface.common import evidence, timed, timed_often
from interface.recording.spec import ENTITIES, TABLE
from .graph import Graph
from .source import keys


ATTEMPTS={
    'full_world':(),
    'without_foreign_detail':('foreign_detail',),
    'without_pop_politics':('pop_politics',),
    'without_pop_needs':('pop_needs',),
    'combined_removals':('foreign_detail','pop_politics','pop_needs')
}
BITS={'foreign_detail':1,'pop_politics':2,'pop_needs':4}
FOREIGN_FACTS={'country_ai_goal','country_profession_population','country_religion_culture_population'}
POLITICAL_FACTS={'pop_movement_support','interest_group_pop'}
FOREIGN_FIELDS={
    'country_standard_of_living_report.'+name for name in (
        'average_standard_of_living_by_political_strength','average_standard_of_living_middle',
        'average_standard_of_living_poor','average_standard_of_living_rich','expected_standard_of_living_by_population',
        'expected_standard_of_living_middle','expected_standard_of_living_poor','expected_standard_of_living_rich')
}|{'pop_status.'+name for name in ('wealth_progress','num_literate','job_satisfaction')}
POLITICAL_FIELDS={'pop_status.political_strength','pop_status.loyalists_and_radicals'}
DESCRIPTIONS={
    'full_world':'All included current-world facts and entities; recurrent history; complete action blocks.',
    'without_foreign_detail':'Remove foreign AI goals and profession/religion/culture population breakdown facts, foreign detailed SOL breakdowns, and foreign pop literacy, wealth progress and job satisfaction. Keep foreign aggregate GDP, population and SOL, every entity and all international relations.',
    'without_pop_politics':'Remove individual pop movement-support and interest-group membership facts, political strength and loyalist/radical attributes. Keep all pops, political entities, aggregate political statistics and other political relations.',
    'without_pop_needs':'Remove state_pop_need breakdown facts. Keep every pop, wealth, food security, professions, state/market goods, consumption and production flows.',
    'combined_removals':'Apply exactly the union of the three listed removals. No additional reduction.'
}


@timed
def plan(graph,data):
    foreign=set()
    for seq in data['history']:
        snapshot=data['states'][seq]
        states={r['state'] for r in snapshot['state_history'] if r['country']!=data['player']}
        foreign.update((seq,'country',r['country']) for r in snapshot['country_history'] if r['country']!=data['player'])
        foreign.update((seq,'pop',r['pop']) for r in snapshot['pop_history'] if r['location'] in states)
        ai={r['country_ai']:r['country'] for r in snapshot['country_ai_history']}
        for name in FOREIGN_FACTS:
            foreign.update((seq,name,tuple(r[k] for k in keys(TABLE[name]))) for r in snapshot[name]
                           if (ai[r['country_ai']] if name=='country_ai_goal' else r['country'])!=data['player'])
    nodes=np.zeros(len(graph.nodes),np.uint8)
    attrs=[]
    for i,node in enumerate(graph.nodes):
        kind=node['kind']
        is_foreign=(node['seq'],kind,node['key']) in foreign
        nodes[i]=(1 if is_foreign and kind in FOREIGN_FACTS else 0)|(2 if kind in POLITICAL_FACTS else 0)|(4 if kind=='state_pop_need' else 0)
        if kind in ENTITIES and nodes[i]:
            raise ValueError(evidence(kind=kind,index=i,removal=nodes[i]))
        attrs.append({key:(1 if is_foreign and key in FOREIGN_FIELDS else 0)|(2 if key in POLITICAL_FIELDS else 0) for key in node['attrs']})
    return nodes,attrs


@timed_often
def bits(name):
    return sum(BITS[component] for component in ATTEMPTS[name])


@timed
def derive(graph,data,name):
    if name=='full_world':
        return graph
    node_bits,attr_bits=plan(graph,data)
    selected=bits(name)
    keep=[i for i in range(len(graph.nodes)) if not node_bits[i]&selected]
    remap={old:new for new,old in enumerate(keep)}
    nodes=[{**graph.nodes[i],'attrs':{key:value for key,value in graph.nodes[i]['attrs'].items() if not attr_bits[i][key]&selected}} for i in keep]
    edges=[(remap[a],remap[b],r,w) for a,b,r,w in graph.edges if a in remap and b in remap]
    if Counter((n['seq'],n['kind'],n['key']) for n in graph.nodes if n['kind'] in ENTITIES)!=Counter((n['seq'],n['kind'],n['key']) for n in nodes if n['kind'] in ENTITIES):
        raise ValueError(evidence(before=sum(n['kind'] in ENTITIES for n in graph.nodes),after=sum(n['kind'] in ENTITIES for n in nodes)))
    return Graph(nodes,edges,remap[graph.player],remap[graph.block],graph.audit)


@timed
def encode_plan(graph,data,encoder,packed):
    node_bits,attrs=plan(graph,data)
    fields={value:key[1] for key,value in encoder.tokens.items() if len(key)>1}
    tokens=np.zeros(len(packed['tokens']),np.uint8)
    for i,attributes in enumerate(attrs):
        begin,end=packed['offsets'][i:i+2]
        if any(attributes.values()):
            tokens[begin:end]=[attributes.get(fields[int(t)],0) for t in packed['tokens'][begin:end]]
    return {'remove_nodes':node_bits,'remove_tokens':tokens}


@timed
def subset(packed,name):
    selected=bits(name)
    if not selected:
        return packed
    keep=packed['remove_nodes']&selected==0
    node_ids=np.flatnonzero(keep)
    remap=np.full(packed['nodes'],-1,np.int32)
    remap[node_ids]=np.arange(len(node_ids),dtype=np.int32)
    counts=np.diff(packed['offsets'])
    token_keep=np.repeat(keep,counts)&(packed['remove_tokens']&selected==0)
    cumulative=np.r_[0,np.cumsum(token_keep)]
    sizes=np.diff(cumulative[packed['offsets']])[keep]
    edge_keep=keep[packed['edge_index']].all(axis=0)
    result={key:packed[key][node_ids] for key in ('kind','current','action')}
    result.update({key:packed[key][token_keep] for key in ('tokens','values')})
    result.update({key:packed[key][edge_keep] for key in ('relation','weight')})
    result.update(offsets=np.r_[0,np.cumsum(sizes)].astype(np.int32),edge_index=remap[packed['edge_index'][:,edge_keep]],
                  player=int(remap[packed['player']]),block=int(remap[packed['block']]),nodes=len(node_ids),audit=packed['audit'])
    return result
