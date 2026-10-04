import bisect

import numpy as np

from interface.common import timed, timed_often
from ..catalogue import CANCELLING, PLAY_ACTIONS
from .features import KINDS, LEADER_ACTIONS, Samples, Versions, queued, resolve

ACTION='action'
CHOICE='answers'
DEFAULT='answers.default'
OFFERED='answers.options_offered'
EFFECT='answers.effects'
DETAIL='answers.effect_details'
ANSWER=(CHOICE,DEFAULT,OFFERED,EFFECT,DETAIL)
BUILDINGS='player.buildings'
METHODS='player.production_methods'
CLOUT='player.interest_group_clout'
APPROVAL='player.interest_group_approval'
GOVERNING='player.interest_groups_in_government'
ROLES='player.character_roles'
IDEOLOGIES='player.character_ideologies'
PEOPLE='player.population_shares'
COUNTRY=(CLOUT,APPROVAL,GOVERNING,ROLES,IDEOLOGIES,PEOPLE)
QUEUE_POSITION='cancelled.queue_position'
QUEUE_PROGRESS='cancelled.queue_progress'
QUEUE=(QUEUE_POSITION,QUEUE_PROGRESS)
SHARES=('lower_strata','middle_strata','upper_strata','radicals','loyalists')
PLAY=('play.relations','play.gdp_ratio','play.prestige_ratio')
PLAY_CONTEXT=('play.truce','play.player_truce_days','play.target_truce_days','play.land_border','play.adjacent_states','play.target_state_adjacent')
PLAY_PACTS=('play.pacts','play.treaty_articles')
LEADER_IDEOLOGIES='interest_group.leader_ideologies'
LEADER_TRAITS='interest_group.leader_traits'
LEADERS=(LEADER_IDEOLOGIES,LEADER_TRAITS)


@timed_often
def entries(batch,lookup):
    found=[]
    for action,params in batch:
        found.append((ACTION,action,1))
        if 'event' in params:
            name,default,offered,effects=lookup.answer(params['event'],params['option'])
            found+=[(CHOICE,name,1),(DEFAULT,str(default),1),(OFFERED,OFFERED,offered)]+[(EFFECT,effect,1) for effect,_ in effects]
            found+=[(DETAIL,f'{effect}={detail}',1) for effect,detail in effects if detail is not None]
        found+=[(f'{action}.{param}',str(resolve(param,kind,params[param],lookup)),1) for param,kind in KINDS[action] if param in params]
        if action in LEADER_ACTIONS:
            for ideology,traits in lookup.leaders(action,params):
                if ideology is not None:
                    found.append((LEADER_IDEOLOGIES,f'{action}.{ideology}',1))
                found+=[(LEADER_TRAITS,f'{action}.{trait}',1) for trait in traits]
        if action in CANCELLING:
            position,progress=queued(lookup.queue,params['state'],params['building_type'])
            found+=[(QUEUE_POSITION,action,position),(QUEUE_PROGRESS,action,progress)]
        if action in PLAY_ACTIONS:
            target=params['country'] if 'country' in params else lookup.state(params['state'])[1]
            found+=[(name,action,value) for name,value in zip(PLAY,lookup.play(target))]
            context,pacts=lookup.context(target,params.get('state'))
            found+=[(name,action,value) for name,value in zip(PLAY_CONTEXT,context)]
            found+=[(name,f'{action}.{kind}',1) for name,kind in pacts]
    return found


@timed_often
def live_holdings(snapshot):
    levels={building:count for building,_,count in snapshot.buildings()}
    clout=snapshot.map('interest_group_stats','interest_group,clout')
    approval=snapshot.map('interest_group_stats','interest_group,approval')
    groups=[(kind,governs,clout[group],approval[group]) for group,kind,governs in snapshot.rows('interest_group','interest_group,interest_group_type,in_government',country=snapshot.player)
            if group in clout]
    characters=dict(snapshot.rows('character','character,ideology',country=snapshot.player))
    roles=[role for character,role in snapshot.rows('character_assigned_role','character,character_role') if character in characters]
    names,rows=snapshot.table('player_population')
    return ([(BUILDINGS,kind,count) for _,kind,count in snapshot.buildings()]+[(METHODS,method,levels[building])
             for building,method in snapshot.rows('building_production_method_active','building,production_method') if building in levels]
            +country(groups,characters.values(),roles,[rows[0][names.index(name)] for name in SHARES]))


@timed_often
def country(groups,ideologies,roles,people):
    found=[]
    for kind,governs,clout,approval in groups:
        found+=[(CLOUT,kind,clout),(APPROVAL,kind,approval),(GOVERNING,kind,float(governs))]
    found+=[(IDEOLOGIES,str(ideology),1) for ideology in ideologies]+[(ROLES,role,1) for role in roles]
    total=sum(people[:3])
    return found+[(PEOPLE,name,value/total) for name,value in zip(SHARES,people)]


class Latest:
    @timed
    def __init__(self,connection,table,key,columns,runs):
        self.index={}
        for run,ident,seq,*values in connection.execute(f'select run_id,{key},seq,{",".join(columns)} from {table} where run_id = any(%s) order by run_id,{key},seq',(runs,)).fetchall():
            seqs,rows=self.index.setdefault((run,ident),([],[]))
            seqs.append(seq)
            rows.append(values)

    def at(self,run,ident,seq):
        seqs,rows=self.index.get((run,ident),([],[]))
        position=bisect.bisect_right(seqs,seq)-1
        return None if position<0 else rows[position]


class Holdings:
    @timed
    def __init__(self,connection,runs):
        self.buildings=Versions(connection,'building_history',['building'],['building_type','state','levels'],runs)
        self.methods=Versions(connection,'building_production_method_active',['building','production_method'],[],runs)
        self.groups=Versions(connection,'interest_group_history',['interest_group'],['interest_group_type','country','in_government'],runs)
        self.stats=Latest(connection,'interest_group_stats','interest_group',['clout','approval'],runs)
        self.characters=Versions(connection,'character_history',['character'],['country','ideology'],runs)
        self.roles=Versions(connection,'character_assigned_role',['character','character_role'],[],runs)
        self.people=Samples(connection,'player_population',list(SHARES),runs)

    @timed_often
    def at(self,lookup):
        found,levels,owners=[],{},{}
        for key in self.buildings.by_run.get(lookup.run,[]):
            now=self.buildings.at(lookup.run,key,lookup.seq)
            if now is None:
                continue
            if now[1] not in owners:
                owners[now[1]]=lookup.state(now[1])[1]
            if owners[now[1]]==lookup.player:
                levels[key[0]]=now[2]
                found.append((BUILDINGS,now[0],now[2]))
        found+=[(METHODS,method,levels[building]) for building,method in self.methods.by_run.get(lookup.run,[])
                if building in levels and self.methods.at(lookup.run,(building,method),lookup.seq) is not None]
        groups=[]
        for key in self.groups.by_run.get(lookup.run,[]):
            now=self.groups.at(lookup.run,key,lookup.seq)
            stats=self.stats.at(lookup.run,key[0],lookup.seq)
            if now is not None and now[1]==lookup.player and stats is not None:
                groups.append((now[0],now[2],*stats))
        characters={}
        for key in self.characters.by_run.get(lookup.run,[]):
            now=self.characters.at(lookup.run,key,lookup.seq)
            if now is not None and now[0]==lookup.player:
                characters[key[0]]=now[1]
        roles=[role for character,role in self.roles.by_run.get(lookup.run,[]) if character in characters and self.roles.at(lookup.run,(character,role),lookup.seq) is not None]
        return found+country(groups,characters.values(),roles,self.people.at(lookup.run,lookup.seq))


class Histograms:
    @timed
    def __init__(self,pauses):
        seen={}
        for found in pauses:
            for name,value in {(name,value) for name,value,_ in found}:
                bins=seen.setdefault(name,{})
                bins[value]=bins.get(value,0)+1
        self.names=sorted(seen)
        self.bins={name:sorted(seen[name],key=lambda value:(-seen[name][value],value)) for name in self.names}
        self.start={}
        self.total=0
        for name in self.names:
            self.start[name]=self.total
            self.total+=len(self.bins[name])
        self.column={(name,value):self.start[name]+position for name in self.names for position,value in enumerate(self.bins[name])}
        self.counts=self.count(pauses)

    @timed_often
    def count(self,pauses,columns=None):
        column=self.column if columns is None else columns
        counts=np.zeros((len(pauses),self.total if columns is None else len(columns)),np.float32)
        for row,found in enumerate(pauses):
            for name,value,weight in found:
                position=column.get((name,value))
                if position is not None:
                    counts[row,position]+=weight
        return counts

    @timed_often
    def selected(self,sizes):
        positions={column:index for index,column in enumerate(self.columns(sizes))}
        return {key:positions[column] for key,column in self.column.items() if column in positions}

    @timed_often
    def columns(self,sizes):
        return [self.start[name]+position for name in self.names for position in range(min(sizes.get(name,0),len(self.bins[name])))]

    @timed_often
    def labels(self,sizes):
        return [f'{name}={value}' for name in self.names for value in self.bins[name][:sizes.get(name,0)]]
