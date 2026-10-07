from collections import defaultdict
from functools import cached_property

import numpy as np

from interface.common import DEFAULT_GAME, timed, timed_often
from interface.recording.spec import TABLE
from interface.script import body, fields, read
from ...catalogue import RECORDED_PARAMS
from ...data.features import Versions

PACT_FIELDS={name:dict(fields(' '.join(found['pact']))) for name,text in read(DEFAULT_GAME/'game','common/diplomatic_actions')
             if 'pact' in (found:=dict(fields(body(text))))}
PACTS=sorted(PACT_FIELDS)
SUBJECT_TYPES={name:found['subject_type'][0] for name,found in PACT_FIELDS.items() if 'subject_type' in found}
ARTICLE_KINDS={name:dict(fields(body(text)))['kind'][0] for name,text in read(DEFAULT_GAME/'game','common/treaty_articles')}
ARTICLES=sorted(ARTICLE_KINDS)
DIRECTIONS=('outgoing','incoming','mutual')
AGREEMENTS={**{f'pact.{kind}':DIRECTIONS[:2] for kind in PACTS},**{f'treaty_article.{kind}':DIRECTIONS for kind in ARTICLES}}
PLAYER='player.diplomacy.'
COUNTERPART='counterpart.diplomacy.'
PLAYER_NUMERIC=[PLAYER+name for name in ('mean_relations','lowest_relations','highest_tension','truce_countries','obligations_owed','obligations_held',
                                       'subjects','liberty_desire','weekly_liberty_desire_change','subject_gdp_ratio',
                                       'bloc_leader','bloc_cohesion','bloc_mandate_progress','bloc_members')]
PLAYER_NUMERIC += [PLAYER+kind+'.'+direction for kind,directions in AGREEMENTS.items() for direction in directions]
PLAYER_CATEGORICAL=[PLAYER+'subject_type',PLAYER+'bloc_identity']
COUNTERPART_NUMERIC=[COUNTERPART+name for name in ('relations','tension','player_truce_days','country_truce_days','player_owes_obligation','owes_player_obligation',
                                                 'gdp_ratio','battalions_ratio','liberty_desire','weekly_liberty_desire_change','same_bloc',
                                                 'player_bloc_leverage','counterpart_bloc_leverage')]
COUNTERPART_CATEGORICAL=[COUNTERPART+'subject_relationship',*[COUNTERPART+kind for kind in AGREEMENTS]]
TABLES={'country':(['country'],['power_bloc','bloc_leader']),
        'power_bloc':(['power_bloc'],['power_bloc_identity','cohesion','mandate_progress']),
        'pact':(['pact'],['first_country','second_country','pact_type']),
        'treaty':(['treaty'],['first_country','second_country','entered_into_force_on','withdrawn']),
        'treaty_article':(['treaty_article'],['treaty','treaty_article_type','source_country','target_country']),
        'player_relation':(['country'],['relations','tension','player_truce','country_truce']),
        'player_obligation':(['country','direction'],[]),
        'country_diplomacy_report':(['country'],['liberty_desire_raw','weekly_liberty_desire_change']),
        'country_economy_report':(['country'],['gdp']),
        'country_military_report':(['country'],['battalions']),
        'country_leverage':(['country','power_bloc'],['leverage'])}
PLAY_TARGETS={'back_initiator':'initiator','lean_towards_initiator':'initiator','back_target':'target','lean_towards_target':'target'}
MISSING='<missing>'


@timed_often
def ratio(first,second):
    return first/second if second>0 else np.nan


@timed_often
def direction(values):
    return 'both' if values=={'outgoing','incoming'} else '+'.join(item for item in DIRECTIONS if item in values) if values else 'none'


class Historical:
    @timed
    def __init__(self,connection,runs):
        self.tables={name:Versions(connection,name+'_history' if name+'_history' in TABLE else name,keys,columns,runs)
                     for name,(keys,columns) in TABLES.items()}

    @timed_often
    def at(self,player,hours,run,seq):
        rows={name:[(*key,*found) for key in table.by_run.get(run,[]) if (found:=table.at(run,key,seq)) is not None]
              for name,table in self.tables.items()}
        return Diplomacy(player,hours,rows)


@timed_often
def live(snapshot):
    return Diplomacy(snapshot.player,snapshot.hours,{name:snapshot.rows(name,','.join(keys+columns)) for name,(keys,columns) in TABLES.items()})


class Diplomacy:
    @timed_often
    def __init__(self,player,hours,rows):
        self.player,self.hours=player,hours
        self.countries={country:(bloc,leader) for country,bloc,leader in rows['country']}
        self.blocs={bloc:(identity,cohesion,mandate) for bloc,identity,cohesion,mandate in rows['power_bloc']}
        self.gdp=dict(rows['country_economy_report'])
        self.battalions=dict(rows['country_military_report'])
        self.liberty={country:(value,change) for country,value,change in rows['country_diplomacy_report']}
        self.leverage={(country,bloc):value for country,bloc,value in rows['country_leverage']}
        foreign=self.countries.keys()-{player}
        self.relations={country:(relations,tension,0. if own is None else max(0.,(own-hours)/24),0. if theirs is None else max(0.,(theirs-hours)/24))
                        for country,relations,tension,own,theirs in rows['player_relation'] if country in foreign}
        self.obligations={kind:{country for country,direction in rows['player_obligation'] if direction==kind and country in foreign}
                          for kind in ('player_owes','owes_player')}
        self.partners={(kind,direction):set() for kind,directions in AGREEMENTS.items() for direction in directions}
        self.arrangements=defaultdict(lambda:defaultdict(set))
        self.overlords=defaultdict(dict)
        self.subjects=defaultdict(set)
        for _,first,second,kind in rows['pact']:
            if first not in self.countries or second not in self.countries:
                continue
            if kind in SUBJECT_TYPES:
                self.overlords[second][first]=SUBJECT_TYPES[kind]
                self.subjects[first].add(second)
            if first==player and second in foreign:
                self.add('pact.'+kind,'outgoing',second)
            elif second==player and first in foreign:
                self.add('pact.'+kind,'incoming',first)
        treaties={treaty:second if first==player else first for treaty,first,second,entered,withdrawn in rows['treaty']
                  if entered is not None and entered<=hours and not withdrawn and player in (first,second) and first!=second}
        for _,treaty,kind,source,target in rows['treaty_article']:
            partner=treaties.get(treaty)
            if partner not in foreign:
                continue
            if ARTICLE_KINDS[kind]=='mutual':
                self.add('treaty_article.'+kind,'mutual',partner)
            elif source==player:
                self.add('treaty_article.'+kind,'outgoing',partner)
            elif target==player:
                self.add('treaty_article.'+kind,'incoming',partner)
        self.counterparts={}

    @timed_often
    def add(self,kind,direction,country):
        self.partners[kind,direction].add(country)
        self.arrangements[country][kind].add(direction)

    @cached_property
    @timed_often
    def overview(self):
        foreign=self.countries.keys()-{self.player}
        relations=[self.relations.get(country,(0.,0.,0.,0.)) for country in foreign]
        subjects=self.subjects[self.player]
        own=self.countries.get(self.player)
        bloc=None if own is None else own[0]
        identity,cohesion,mandate=self.blocs.get(bloc,('none' if own is not None and bloc is None else MISSING,np.nan,np.nan))
        subject_type='|'.join(sorted(set(self.overlords[self.player].values()))) or 'independent'
        values=[np.mean([row[0] for row in relations]) if relations else np.nan,min((row[0] for row in relations),default=np.nan),
                max((row[1] for row in relations),default=np.nan),sum(own>0 or theirs>0 for _,_,own,theirs in relations),
                len(self.obligations['player_owes']),len(self.obligations['owes_player']),len(subjects),*self.liberty.get(self.player,(np.nan,np.nan)),
                ratio(sum(self.gdp.get(subject,np.nan) for subject in subjects),self.gdp.get(self.player,np.nan)),
                np.nan if own is None else float(own[1]),cohesion,mandate,
                np.nan if own is None else sum(found==bloc for found,_ in self.countries.values()) if bloc is not None else 0]
        return {**dict(zip(PLAYER_NUMERIC[:14],values)),**{PLAYER+kind+'.'+direction:len(partners) for (kind,direction),partners in self.partners.items()},
                PLAYER+'subject_type':MISSING if own is None else subject_type,PLAYER+'bloc_identity':identity}

    @timed_often
    def target(self,country):
        if country is None or country==self.player:
            return {}
        if country in self.counterparts:
            return self.counterparts[country]
        if country not in self.countries or self.player not in self.countries:
            return {**dict.fromkeys(COUNTERPART_NUMERIC,np.nan),**dict.fromkeys(COUNTERPART_CATEGORICAL,MISSING)}
        relations,tension,own_truce,their_truce=self.relations.get(country,(0.,0.,0.,0.))
        bloc=self.countries[self.player][0]
        other_bloc=self.countries[country][0]
        relationship=('subject' if country in self.subjects[self.player] else 'overlord' if country in self.overlords[self.player]
                      else 'fellow_subject' if self.overlords[self.player].keys()&self.overlords[country].keys() else 'unrelated')
        values=[relations,tension,own_truce,their_truce,float(country in self.obligations['player_owes']),float(country in self.obligations['owes_player']),
                ratio(self.gdp.get(self.player,np.nan),self.gdp.get(country,np.nan)),ratio(self.battalions.get(self.player,np.nan),self.battalions.get(country,np.nan)),
                *self.liberty.get(country,(np.nan,np.nan)),float(bloc is not None and bloc==other_bloc),
                self.leverage.get((country,bloc),0.) if bloc is not None else np.nan,
                self.leverage.get((self.player,other_bloc),0.) if other_bloc is not None else np.nan]
        found={**dict(zip(COUNTERPART_NUMERIC,values)),COUNTERPART+'subject_relationship':relationship,
               **{COUNTERPART+kind:direction(self.arrangements[country][kind]) for kind in AGREEMENTS}}
        self.counterparts[country]=found
        return found


@timed_often
def counterpart(name,params,point):
    expected=dict(RECORDED_PARAMS[name])
    player=point.state.player
    if expected.get('country')=='country':
        return params['country'] if params['country']!=player else None
    if expected.get('state')=='state' or expected.get('building')=='building':
        state=params['state'] if 'state' in params else point.state.home(params['building'])
        country=point.state.state(state)[1]
        return country if country!=player else None
    if expected.get('treaty')=='treaty':
        treaty=point.entity('treaty',params['treaty'])
        if treaty is None:
            return None
        countries={treaty['first_country'],treaty['second_country']}
        others=countries-{player,None}
        return next(iter(others)) if player in countries and len(others)==1 else None
    if expected.get('power_bloc')=='power_bloc':
        leaders=[country for country,(bloc,leader) in point.diplomacy.countries.items() if bloc==params['power_bloc'] and leader and country!=player]
        return leaders[0] if len(leaders)==1 else None
    if expected.get('diplomatic_play')=='diplomatic_play' or expected.get('war')=='war':
        if 'war' in params:
            war=point.entity('war',params['war'])
            play=None if war is None else point.entity('diplomatic_play',war['diplomatic_play'])
        else:
            play=point.entity('diplomatic_play',params['diplomatic_play'])
        if play is None:
            return None
        if name in PLAY_TARGETS:
            country=play[PLAY_TARGETS[name]]
            return country if country!=player else None
        countries={play['initiator'],play['target']}
        others=countries-{player,None}
        return next(iter(others)) if player in countries and len(others)==1 else None
    return None
