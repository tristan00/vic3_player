import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import time

import psycopg
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from interface.common import timed, timed_often
from interface.options.stored import read_table
from interface.recording.spec import ENTITIES, TABLE
from interface.recording.store import DSN
from loop.run import redraw
from .graph import Builder, Graph, audit
from ...catalogue import BY_NAME
from .schema import FULL_WORLD, GRAPH_VERSION, OMIT, PARAMETERS
from .source import blocks, geography, keys, save
from .spatial import add_spatial


EXCLUDED={
    'ui_open_window':'UI state',
    'player_message':'UI message feed',
    'player_alert':'UI alert feed',
    'player_state_alert':'UI alert feed',
    'player_ignored_decision':'UI preference',
    'player_production_method_available':'Action availability',
    'player_formable_country':'Action availability',
    'player_releasable_country':'Action availability',
    'player_decision':'Action availability',
    'player_journal_button':'Action availability',
    'player_diplomatic_option':'Action availability',
    'player_diplomatic_option_state':'Action availability',
    'player_character_interaction':'Action availability',
    'state_decree_valid':'Action availability',
    'building_privatization_enabled':'Action availability',
    'formation_upgrade_unit_type':'Action availability',
    'formation_borrow_setting':'UI selection options',
    'event_option':'UI option text and availability'
}
WORLD_TABLES=tuple(name for name in TABLE if name not in EXCLUDED)
FIELD_EXCLUSIONS=OMIT|{'deployable','retrofittable','num_available_negotiations','num_states_that_can_be_incorporated','scope_target'}
SCOPES={'ctry':'country','cul':'culture','ig':'interest_group','journal_entry':'journal_entry','state':'state'}
KINDS={'market_goods':'market_good','state_goods':'state_good'}
ATTRIBUTES={name:tuple((col,name+'.'+col.name) for col in TABLE[name].keys+TABLE[name].columns) for name in WORLD_TABLES}


@timed
def read_world(connection,run,seq):
    return WorldReader(connection,run).read(seq)


class WorldReader:
    @timed
    def __init__(self,connection,run):
        self.connection,self.run=connection,run
        self.dates=dict(connection.execute('select seq,game_date from snapshot where run_id=%s order by seq',(run,)))
        vocabulary_names=sorted({c.vocabulary for name in WORLD_TABLES for c in TABLE[name].keys+TABLE[name].columns if c.vocabulary})
        enum_names=sorted({c.enum for name in WORLD_TABLES for c in TABLE[name].keys+TABLE[name].columns if c.enum})
        self.vocabulary={name:dict(connection.execute(f'select {name},name from {name}')) for name in vocabulary_names}
        self.enums={name:dict(connection.execute(f'select {name},name from {name}')) for name in enum_names}
        self.player=connection.execute('select player_country from run where run_id=%s',(run,)).fetchone()[0]
        self.geography=geography(connection,run)
        self.actions=blocks(connection,run)

    @timed
    def snapshot(self,at):
        connection,run=self.connection,self.run
        snapshot={}
        for name in WORLD_TABLES:
            table=TABLE[name]
            if table.kind=='sample':
                identity=keys(table)
                order=','.join([*identity,'date desc nulls last','n desc'])
                distinct='distinct on ('+','.join(identity)+')' if identity else ''
                limit='' if identity else ' limit 1'
                live=f' and {table.owner} in (select {table.owner} from {table.owner}_at(%s,%s))' if table.owner else ''
                args=(run,at,self.dates[at],run,at) if table.owner else (run,at,self.dates[at])
                cursor=connection.execute(f'select {distinct} * from {name} where run_id=%s and seq<=%s and (date is null or date<=%s){live} order by {order}{limit}',args)
                columns=[c.name for c in cursor.description]
                rows=cursor.fetchall()
            else:
                columns,rows=read_table(connection,name,run,at)
            labels={label[:63]:label for label in ('run_id','seq','n','date',*keys(table),*[c.name for c in table.columns])}
            columns=[labels[label] for label in columns]
            snapshot[name]=[dict(zip(columns,row)) for row in rows]
        return snapshot

    @timed
    def read(self,seq):
        if seq not in self.dates:
            raise ValueError('The requested snapshot does not exist')
        return {'run':self.run,'seq':seq,'player':self.player,'history':[seq],
                'dates':{seq:self.dates[seq]},'states':{seq:self.snapshot(seq)},
                'geography':self.geography,'vocabulary':self.vocabulary,'enums':self.enums,'tables':WORLD_TABLES,
                'action_history':{}}


class WorldBuilder(Builder):
    @timed
    def __init__(self,data):
        super().__init__(FULL_WORLD,data['vocabulary'],data['dates'][data['seq']])
        self.data=data
        self.missing=[]
        self.scope_targets=[]
        self.coverage=[]
        self.spatial=[]
        self.semantics={}
        self.definitions={}
        self.audit['graph_version']=GRAPH_VERSION

    def definition(self,kind,value,seq,hour):
        key=(kind,value)
        if key not in self.definitions:
            name=self.vocabulary[kind][value]
            self.definitions[key]=self.node('definition.'+kind,name,seq,hour,{'name':name})
        return self.definitions[key]

    def endpoint(self,kind,value,seq,hour,table,field,source):
        target=self.find(seq,kind,value)
        if target is None:
            target=self.node('unobserved.'+kind,value,seq,hour,{})
            self.nodes[target]['observation']='Referenced identity has no live recorded entity at this snapshot'
            self.missing.append({'seq':seq,'table':table,'field':field,'source':source,'target_kind':kind,'target':value})
        return target

    def attach(self,name,row,node,seq,hour):
        table=TABLE[name]
        attrs=self.nodes[node]['attrs']
        provenance=self.nodes[node].setdefault('sources',{})
        provenance[name]={'observed_seq':row['seq']}
        if table.kind=='sample':
            provenance[name]['sample_date']=row['date']
            provenance[name]['sample_index']=row['n']
        for col,field in ATTRIBUTES[name]:
            value=row[col.name]
            if value is None or value in col.sentinels:
                continue
            if col.entity:
                target=self.endpoint(col.entity,value,seq,hour,name,col.name,node)
                self.edge(node,target,field)
            elif col.name in FIELD_EXCLUSIONS:
                if col.vocabulary=='localization_key':
                    self.nodes[node].setdefault('labels',{})[col.name]=self.vocabulary[col.vocabulary][value]
                elif col.name in ('current_location','target_location','target_other','invasion'):
                    self.nodes[node].setdefault('opaque_fields',{})[field]=value
            elif col.vocabulary:
                attrs[field]=self.vocabulary[col.vocabulary][value]
                if col.vocabulary not in ('scope_name','localization_key'):
                    self.edge(node,self.definition(col.vocabulary,value,seq,hour),field)
            elif col.enum:
                label=self.data['enums'][col.enum][value]
                attrs[field]=str(value) if label is None else label
            elif col.check or col.kind=='text':
                attrs[field]=str(value)
            else:
                attrs[field]=float((hour-value)/24 if col.kind=='game_hours' else value)
        if 'scope_target' in row:
            kind=self.data['enums']['scope_type'][row['scope_type']]
            target_kind=SCOPES.get(kind)
            value=row['scope_target']
            if kind=='none' and value==0:
                return
            if target_kind in ENTITIES and self.find(seq,target_kind,value) is not None:
                self.edge(node,self.find(seq,target_kind,value),name+'.scope_target')
            else:
                reference={'seq':seq,'table':name,'node':node,'scope':kind,'scope_type':row['scope_type'],'value':value}
                self.scope_targets.append(reference)
                self.nodes[node]['opaque_scope_target']=reference

    @timed
    def snapshot(self,seq):
        snapshot=self.data['states'][seq]
        hour=self.data['dates'][seq]
        raw={kind:{row[kind]:row for row in snapshot.get(kind+'_history',[])} for kind in ENTITIES}
        for kind in ENTITIES:
            for key,row in sorted(raw[kind].items()):
                node=self.node(kind,key,seq,hour,{'is_player':float(key==self.data['player'])} if kind=='country' else {})
        for name in self.data['tables']:
            table=TABLE[name]
            rows=snapshot[name]
            identity=keys(table)
            represented=0
            for row in rows:
                key=tuple(row[k] for k in identity)
                if table.kind=='history':
                    node=self.find(seq,table.owner,row[table.owner])
                elif table.owner and not table.keys:
                    node=self.endpoint(table.owner,row[table.owner],seq,hour,name,table.owner,None)
                elif table.kind=='singleton' or table.kind=='sample' and table.owner is None and not table.keys:
                    node=self.find(seq,'country',self.data['player'])
                else:
                    node=self.node(KINDS.get(name,name),key,seq,hour,{})
                    if table.owner:
                        parent=self.endpoint(table.owner,row[table.owner],seq,hour,name,table.owner,node)
                        self.edge(parent,node,name+'.member')
                    elif table.scope=='player':
                        self.edge(self.find(seq,'country',self.data['player']),node,name+'.player')
                self.attach(name,row,node,seq,hour)
                represented+=1
            self.coverage.append({'seq':seq,'table':name,'scope':table.scope,'source_rows':len(rows),'represented_rows':represented})
        self.geography(raw,seq,hour,self.data['geography'])
        for province,region,terrain,area,x,y in self.data['geography']['provinces']:
            node=self.find(seq,'province',province)
            if node is not None:
                self.nodes[node]['attrs'].update({'area_pixels':float(area),'x':float(x),'y':float(y)})
                if region is not None:
                    self.edge(node,self.definition('state_region',region,seq,hour),'province.region')
                if terrain is not None:
                    self.nodes[node]['attrs']['terrain']=terrain
                    terrain_node=self.node('definition.terrain',terrain,seq,hour,{'name':terrain})
                    self.edge(node,terrain_node,'province.terrain')
        for row in snapshot['state_goods']:
            state=row['state']
            good=self.find(seq,'state_good',(state,row['goods']))
            owner=raw['state'].get(state,{}).get('country')
            market=raw['country'].get(owner,{}).get('market')
            self.edge(good,self.find(seq,'market_good',(market,row['goods'])),'state_good.market')
        for row in snapshot['building_goods']:
            building=self.find(seq,'building',row['building'])
            state=raw['building'].get(row['building'],{}).get('state')
            good=self.find(seq,'state_good',(state,row['goods']))
            for direction in ('input','output','slave_input'):
                if row[direction] is not None and row[direction]!=0:
                    self.edge(building,good,'building.'+direction,row[direction])
        self.spatial.append(add_spatial(self,raw,seq,hour,self.data['geography']))

    @timed
    def semantic_index(self,seq,player):
        snapshot=self.data['states'][seq]
        owned={r['state'] for r in snapshot['state_history'] if r['country']==player}
        buildings={r['building']:r['state'] for r in snapshot['building_history']}
        formations={r['formation'] for r in snapshot['formation_history'] if r['country']==player}
        market=next(r['market'] for r in snapshot['country_history'] if r['country']==player)
        index=defaultdict(list)
        for i,found in enumerate(self.nodes):
            if found['seq']!=seq:
                continue
            kind,key,attrs=found['kind'],found['key'],found['attrs']
            if kind in ('state_good','market_good'):
                field='state_goods.goods' if kind=='state_good' else 'market_goods.goods'
                if key[0] in owned if kind=='state_good' else key[0]==market:
                    index['goods',attrs.get(field)].append((i,'action.affects_goods',key[0] if kind=='state_good' else None))
            if kind=='building' and buildings[key] in owned:
                index['building_type',attrs.get('building_history.building_type')].append((i,'action.affects_building_type',buildings[key]))
            if kind=='building_production_method_active' and buildings.get(key[0]) in owned:
                index['production_method',attrs.get('building_production_method_active.production_method')].append((i,'action.affects_production_method',None))
            if kind=='formation' and key in formations:
                for name in ('mobilize_all_armies','demobilize_all_armies','upgrade_all_units'):
                    index['action',name].append((i,'action.affects_formation',None))
            if kind=='player_construction_queue_item':
                for name in ('pause_construction','resume_construction'):
                    index['action',name].append((i,'action.affects_queue',None))
        return index

    @timed
    def semantic(self,node,name,params,seq,player):
        if seq not in self.semantics:
            self.semantics[seq]=self.semantic_index(seq,player)
        index=self.semantics[seq]
        built=[('building_type',BY_NAME[name].subject)] if BY_NAME[name].domain=='construction' and BY_NAME[name].subject else []
        targets=[item for key,value in [('action',name),*built,*params.items()] for item in index.get((key,value),())
                 if item[2] is None or 'state' not in params or item[2]==params['state']]
        for target,relation,state in sorted(targets):
            self.edge(node,target,relation)

    @timed
    def candidate(self,actions,seq,hour,player):
        block=super().candidate(actions,seq,hour,player)
        for i,(name,params) in enumerate(actions):
            node=self.find(seq,'action',i)
            for param,value in params.items():
                kind=PARAMETERS[name][param]
                if kind in self.vocabulary:
                    target=self.find(seq,'definition.'+kind,value)
                    if target is not None:
                        self.edge(node,target,'action.parameter.'+param+'_definition')
        self.edge(self.find(seq,'world_state','snapshot'),block,'candidate.context',reverse=False)
        return block


@timed
def build_world(data,actions=None):
    if tuple(data.get('tables',()))!=WORLD_TABLES:
        raise ValueError('Full world requires the complete recording schema')
    if 'map' not in data['geography']:
        raise ValueError('Full world requires recorded map raster and coordinate geometry; reload the source snapshot')
    seq=data['seq']
    data={**data,'history':[seq],'action_history':{}}
    builder=WorldBuilder(data)
    builder.snapshot(seq)
    state=builder.node('world_state','snapshot',seq,data['dates'][seq],{})
    for row in data['states'][seq]['country_history']:
        builder.edge(state,builder.find(seq,'country',row['country']),'world_state.country')
    block=state if actions is None else builder.candidate(actions,seq,data['dates'][seq],data['player'])
    builder.audit.update(nodes=len(builder.nodes),edges=len(builder.edges))
    graph=Graph(builder.nodes,builder.edges,builder.find(seq,'country',data['player']),block,dict(builder.audit))
    summary=audit(graph,data['dates'][seq])
    expected=Counter(kind for kind in ENTITIES for _ in data['states'][seq].get(kind+'_history',[]))
    observed=Counter(n['kind'] for n in graph.nodes if n['kind'] in ENTITIES)
    if expected!=observed or any(c['source_rows']!=c['represented_rows'] for c in builder.coverage):
        raise ValueError('Full world graph lost recorded entities or fact rows')
    if any(n['sources'][name]['observed_seq']>seq for n in graph.nodes for name in n.get('sources',{})):
        raise ValueError('Full world graph contains future facts')
    summary.update(run=data['run'],seq=seq,history=[seq],coverage=builder.coverage,
                   missing_entity_records=builder.missing,opaque_scope_targets=builder.scope_targets,
                   excluded_tables=EXCLUDED,excluded_fields=sorted(FIELD_EXCLUSIONS),components=components(graph),
                   graph_version=GRAPH_VERSION,spatial=builder.spatial,action_history=[],
                   map={key:data['geography']['map'][key] for key in ('width','height','wrap_x','unmapped_pixels','coordinate_frame')})
    return graph,summary


@timed
def components(graph):
    edges=graph.connections()
    matrix=coo_matrix((np.ones(edges.shape[1],np.uint8),(edges[0],edges[1])),shape=(len(graph.nodes),len(graph.nodes))).tocsr()
    count,labels=connected_components(matrix,directed=False)
    sizes=np.bincount(labels)
    isolated=np.flatnonzero(sizes[labels]==1).tolist()
    return {'count':int(count),'sizes':sorted(sizes.tolist(),reverse=True),'isolated_nodes':isolated,
            'isolated_types':dict(Counter(graph.nodes[i]['kind'] for i in isolated))}


@timed
def export(root,run,seq):
    started=time.monotonic()
    output=root/'full_world'
    output.mkdir(parents=True,exist_ok=True)
    with psycopg.connect(DSN) as connection:
        connection.execute('set transaction isolation level repeatable read read only')
        data=read_world(connection,run,seq)
        seed=20261001+run*1009+seq
        snapshot,blocks=redraw(connection,run,seq,30,seed)
    save(output/'source.pkl.gz',data)
    (output/'candidates.json').write_text(json.dumps({'seed':seed,'generator':'loop.run.redraw','blocks':blocks},indent=2),encoding='utf-8')
    from .world_catalog import catalog
    catalog(root,data,blocks[0])
    print(json.dumps({'run':run,'seq':seq,'seconds':time.monotonic()-started}),flush=True)


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--run',type=int,required=True)
    parser.add_argument('--seq',type=int,required=True)
    args=parser.parse_args()
    export(args.root,args.run,args.seq)


if __name__=='__main__':
    main()
