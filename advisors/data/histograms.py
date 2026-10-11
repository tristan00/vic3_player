import numpy as np

from interface.common import timed, timed_often
from ..catalogue import CANCELLING, PLAY_ACTIONS, SITED
from .features import KINDS, LEADER_ACTIONS, SITE, Samples, Versions, located, queued, resolve

ACTION='action'
CHOICE='answers'
DEFAULT='answers.default'
OFFERED='answers.options_offered'
EFFECT='answers.effects'
DETAIL='answers.effect_details'
ANSWER=(CHOICE,DEFAULT,OFFERED,EFFECT,DETAIL)
BUILDINGS='player.buildings'
METHODS='player.production_methods'
ROLES='player.character_roles'
IDEOLOGIES='player.character_ideologies'
PEOPLE='player.population_shares'
COUNTRY=(ROLES,IDEOLOGIES,PEOPLE)
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
def entries(batch,lookup,families=None):
    found=[]
    sites={}
    wanted=lambda name:families is None or name in families
    for action,params in batch:
        if wanted(ACTION):
            found.append((ACTION,action,1))
        if action in SITED and (families is None or families.intersection(SITE)):
            sites.setdefault(SITED[action],[]).append(lookup.site(*located(action,params,lookup)))
        if 'event' in params and (families is None or families.intersection(ANSWER)):
            name,default,offered,effects=lookup.answer(params['event'],params['option'])
            found+=[(CHOICE,name,1),(DEFAULT,str(default),1),(OFFERED,OFFERED,offered)]+[(EFFECT,effect,1) for effect,_ in effects]
            found+=[(DETAIL,f'{effect}={detail}',1) for effect,detail in effects if detail is not None]
        found+=[(f'{action}.{param}',str(resolve(param,kind,params[param],lookup)),1) for param,kind in KINDS[action] if param in params and wanted(f'{action}.{param}')]
        if action in LEADER_ACTIONS and (families is None or families.intersection(LEADERS)):
            for ideology,traits in lookup.leaders(action,params):
                if ideology is not None:
                    found.append((LEADER_IDEOLOGIES,f'{action}.{ideology}',1))
                found+=[(LEADER_TRAITS,f'{action}.{trait}',1) for trait in traits]
        if action in CANCELLING and (families is None or families.intersection(QUEUE)):
            position,progress=queued(lookup.queue,params['state'],params['building_type'])
            found+=[(QUEUE_POSITION,action,position),(QUEUE_PROGRESS,action,progress)]
        if action in PLAY_ACTIONS and (families is None or families.intersection((*PLAY,*PLAY_CONTEXT,*PLAY_PACTS))):
            target=params['country'] if 'country' in params else lookup.state(params['state'])[1]
            if families is None or families.intersection(PLAY):
                found+=[(name,action,value) for name,value in zip(PLAY,lookup.play(target))]
            if families is None or families.intersection((*PLAY_CONTEXT,*PLAY_PACTS)):
                context,pacts=lookup.context(target,params.get('state'))
                found+=[(name,action,value) for name,value in zip(PLAY_CONTEXT,context)]
                found+=[(name,f'{action}.{kind}',1) for name,kind in pacts]
    for kind,rows in sites.items():
        for name,values in zip(SITE,zip(*rows)):
            known=[value for value in values if value==value]
            if known:
                found.append((name,kind,sum(known)/len(known)))
    return found if families is None else [item for item in found if item[0] in families]


@timed_often
def live_holdings(snapshot):
    levels={building:count for building,_,count in snapshot.buildings()}
    characters=dict(snapshot.rows('character','character,ideology',country=snapshot.player))
    roles=[role for character,role in snapshot.rows('character_assigned_role','character,character_role') if character in characters]
    names,rows=snapshot.table('player_population')
    return ([(BUILDINGS,kind,count) for _,kind,count in snapshot.buildings()]+[(METHODS,method,levels[building])
             for building,method in snapshot.rows('building_production_method_active','building,production_method') if building in levels]
            +country(characters.values(),roles,[rows[0][names.index(name)] for name in SHARES]))


@timed_often
def country(ideologies,roles,people):
    found=[(IDEOLOGIES,str(ideology),1) for ideology in ideologies]+[(ROLES,role,1) for role in roles]
    total=sum(people[:3])
    return found+[(PEOPLE,name,value/total) for name,value in zip(SHARES,people)]


class Holdings:
    @timed
    def __init__(self,connection,runs,families=None):
        self.families={BUILDINGS,METHODS,*COUNTRY} if families is None else set(families)
        if self.families.intersection((BUILDINGS,METHODS)):
            self.buildings=Versions(connection,'building_history',['building'],['building_type','state','levels'],runs)
        if METHODS in self.families:
            self.methods=Versions(connection,'building_production_method_active',['building','production_method'],[],runs)
        if self.families.intersection((ROLES,IDEOLOGIES)):
            self.characters=Versions(connection,'character_history',['character'],['country','ideology'],runs)
        if ROLES in self.families:
            self.roles=Versions(connection,'character_assigned_role',['character','character_role'],[],runs)
        if PEOPLE in self.families:
            self.people=Samples(connection,'player_population',list(SHARES),runs)

    @timed_often
    def at(self,lookup):
        found,levels,owners=[],{},{}
        for key in self.buildings.by_run.get(lookup.run,[]) if self.families.intersection((BUILDINGS,METHODS)) else ():
            now=self.buildings.at(lookup.run,key,lookup.seq)
            if now is None:
                continue
            if now[1] not in owners:
                owners[now[1]]=lookup.state(now[1])[1]
            if owners[now[1]]==lookup.player:
                levels[key[0]]=now[2]
                if BUILDINGS in self.families:
                    found.append((BUILDINGS,now[0],now[2]))
        if METHODS in self.families:
            found+=[(METHODS,method,levels[building]) for building,method in self.methods.by_run.get(lookup.run,[])
                    if building in levels and self.methods.at(lookup.run,(building,method),lookup.seq) is not None]
        characters={}
        for key in self.characters.by_run.get(lookup.run,[]) if self.families.intersection((ROLES,IDEOLOGIES)) else ():
            now=self.characters.at(lookup.run,key,lookup.seq)
            if now is not None and now[0]==lookup.player:
                characters[key[0]]=now[1]
        if IDEOLOGIES in self.families:
            found.extend((IDEOLOGIES,str(ideology),1) for ideology in characters.values())
        if ROLES in self.families:
            found.extend((ROLES,role,1) for character,role in self.roles.by_run.get(lookup.run,[]) if character in characters and self.roles.at(lookup.run,(character,role),lookup.seq) is not None)
        if PEOPLE in self.families:
            found.extend(country([],[],self.people.at(lookup.run,lookup.seq)))
        return found


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
