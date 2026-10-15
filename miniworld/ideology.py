import re

from interface.script import blocks, body, read, scalar
from . import GAME, timed

PARTS=('country_trigger','interest_group_leader_trigger','non_interest_group_leader_trigger')
ROOT=re.compile(r'\broot\b')


@timed
def scripts():
    triggers=[]
    entries=[]
    for key,block in read(GAME,'common/ideologies'):
        if scalar(block,'character_ideology')!='yes': continue
        parts=dict(blocks(body(block)))
        found={name:body(text) for name,text in parts.items() if name in PARTS}
        country,leader,other=(found.get(name,'') for name in PARTS)
        leader=leader if 'interest_group_leader_weight' in parts else 'always = no'
        other=ROOT.sub('scope:mw_character',other) if 'non_interest_group_leader_weight' in parts else 'always = no'
        triggers.append(f'mw_eligible_{key} = {{\n\towner = {{\n{country}\n\t}}\n\tOR = {{\n\t\tAND = {{\n\t\t\tis_interest_group_leader = yes\n'
                        f'\t\t\tinterest_group ?= {{\n{leader}\n\t\t\t}}\n\t\t}}\n\t\tAND = {{\n\t\t\tis_interest_group_leader = no\n{other}\n\t\t}}\n\t}}\n}}\n')
        entries.append(f'\t\t1 = {{\n\t\t\ttrigger = {{ mw_eligible_{key} = yes }}\n\t\t\tset_ideology = ideology:{key}\n\t\t}}\n')
    return ''.join(triggers),'mw_shuffle_ideology = {\n\tsave_scope_as = mw_character\n\trandom_list = {\n'+''.join(entries)+'\t}\n}\n'


@timed
def started(share):
    return (f'mw_shuffle_ideologies = {{\n\teffect = {{\n\t\tevery_country = {{\n\t\t\tevery_scope_character = {{\n\t\t\t\trandom = {{\n'
            f'\t\t\t\t\tchance = {int(round(share*100))}\n\t\t\t\t\tmw_shuffle_ideology = yes\n\t\t\t\t}}\n\t\t\t}}\n\t\t}}\n\t}}\n}}\n')
