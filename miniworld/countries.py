import json
from collections import Counter, defaultdict
import re
from pathlib import Path

import numpy as np

from interface.script import blocks, body, clean, read, scalar
from . import GAME, timed, timed_often

CALIBRATION=Path(__file__).with_name('calibration.json')
COPIED=('countries','characters','governments')
GENERIC=('ai',)
CONDITIONAL=('global','political_movements')
REPLACED=('ai','global','political_movements','population','production_methods','states','pops','buildings','military_formations','military_deployments',
         'diplomacy','diplomatic_plays','lobbies','power_blocs','treaties','trade')
DROPPED={'set_capital','set_market_capital','add_company','create_diplomatic_pact'}
SPENT={'add_treasury','change_infamy'}
NEAREST=5
CONTROL=('if','else_if','else')
REFERENCE=re.compile(r'(?<!\?=\s)(?<!\?=)(?<!exists = )(?<!exists=)\bc:([A-Z][A-Z0-9]{2})\b(?!\s*\?=)')
MENTION=re.compile(r'\bc:([A-Z][A-Z0-9]{2})\b')
VANILLA_STATE=re.compile(r'\bs:STATE_(?!MW_)|\bSTATE_(?!MW_)\w|\bsr:(?!region_mw_)|\bregion_state:|\bp:x[0-9A-Fa-f]|\bgeographic_region_\w')
STATURE=re.compile(r'\b(?:\w*(?:prestige|influence|infamy|tax|minting|expenses|gold_reserve|loan|battle|authority|bureaucracy|construction|maneuvers)|unit_)\w*\s*=')
STARTING=re.compile(r'\b(effect_starting_pop_(?:wealth|literacy)_\w+)\s*=\s*yes')
SPENDING=re.compile(r'\b(?:'+'|'.join(sorted(SPENT))+r')\b')
JOURNAL=re.compile(r'add_journal_entry\s*=\s*(?:\{\s*type\s*=\s*(\w+)[^}]*\}|(\w+))')
EVENT=re.compile(r'trigger_event\s*=\s*(?:\{[^}]*?\bid\s*=\s*([\w.-]+)[^}]*\}|([\w-]+\.\d+))')
CULTURE=re.compile(r'(add|remove)_primary_culture\s*=\s*cu:(\w+)')
RULER=re.compile(r'\bruler\s*=\s*yes|\brole\s*=\s*(?:character_role_)?ruler\b')
TEMPLATE=re.compile(r'\btemplate\s*=\s*(\w+)')
NAME=re.compile(r'[A-Za-z_][\w.-]*')
MARKED=re.compile(r'(?:add_modifier|set_variable)\s*=\s*(?:\{[^}]*?\bname\s*=\s*(\w+)|(\w+))')
TOKEN=re.compile(r'"(?:\\.|[^"\\])*"|\?=|[{}]|[^\s{}=?]+|=')


@timed
def candidates():
    definitions=dict(read(GAME,'common/country_definitions'))
    owners=set(re.findall(r'country\s*=\s*c:(\w+)',(GAME/'common/history/states/00_states.txt').read_text(encoding='utf-8-sig')))
    return {tag:block for tag,block in definitions.items() if tag in owners and scalar(block,'country_type')=='recognized'}


@timed
def pick(rng,known,count):
    return sorted(rng.choice(sorted(known),count,replace=False).tolist())


@timed
def populations():
    found=Counter()
    for _,top in read(GAME,'common/history/pops'):
        for state,inner in blocks(body(top)):
            for region,group in blocks(body(inner)):
                found[state[2:],region.split(':',1)[1]]+=sum(int(n) for n in re.findall(r'size\s*=\s*(\d+)',group))
    return found


@timed
def incorporation():
    found=defaultdict(list)
    for _,top in read(GAME,'common/history/states'):
        for state,inner in blocks(body(top)):
            for kind,made in blocks(body(inner)):
                if kind=='create_state': found[re.search(r'\bcountry\s*=\s*c:(\w+)',made)[1]].append((state[2:],bool(re.search(r'\bstate_type\s*=\s*unincorporated\b',made))))
    return found


@timed_often
def held(people):
    out=Counter()
    for (_,tag),n in people.items(): out[tag]+=n
    return out


@timed
def tiers(people):
    found=held(people)
    return sorted((float(np.log(found[tag])),scalar(block,'tier')) for tag,block in read(GAME,'common/country_definitions')
                  if scalar(block,'country_type')=='recognized' and found[tag])


@timed
def wealth(known,vanilla):
    researched=technologies({tag:vanilla[tag] for tag in known})
    _,found=copied('population',set(known))
    return sorted((len(researched[tag]),tag,STARTING.findall(found.get(tag,''))) for tag in known)


@timed
def population(rng,found,techs):
    counts=np.array([n for n,_,_ in found])
    lines=[]
    for tag,known in sorted(techs.items()):
        others=np.array([other!=tag for _,other,_ in found])
        distance=np.where(others,np.abs(counts-len(known)),np.inf)
        _,_,effects=found[int(rng.choice(np.flatnonzero(distance<=np.sort(distance)[NEAREST-1])))]
        if effects: lines.append(f'\tc:{tag} ?= {{\n'+''.join(f'\t\t{effect} = yes\n' for effect in effects)+'\t}\n')
    return 'POPULATION = {\n'+''.join(lines)+'}\n'


@timed
def tiered(rng,found,population):
    logs=np.array([p for p,_ in found])
    out={}
    for tag,people in sorted(population.items()):
        distance=np.abs(logs-np.log(people))
        out[tag]=found[int(rng.choice(np.flatnonzero(distance<=np.sort(distance)[NEAREST-1])))][1]
    return out


@timed
def definitions(keys,tiers):
    out={}
    for path in sorted((GAME/'common/country_definitions').glob('*.txt')):
        content=clean(path)
        for tag,block in blocks(content):
            made=re.sub(r'\n\s*is_named_from_capital\s*=\s*yes','',block)
            made=re.sub(r'capital\s*=\s*STATE_\w+',f'capital = {keys[tag]}',made,count=1) if tag in keys else re.sub(r'\n\s*capital\s*=\s*STATE_\w+','',made)
            if tag in tiers: made=re.sub(r'\btier\s*=\s*\w+',f'tier = {tiers[tag]}',made,count=1)
            content=content.replace(block,made)
        out[path.name]=content
    return out


@timed_often
def statements(text):
    found=[]
    depth=0;key=None;begin=None;expect=False
    for m in TOKEN.finditer(text):
        t=m[0]
        if t=='{':
            depth+=1
        elif t=='}':
            depth-=1
            if depth==0 and expect:
                found.append((key,text[begin:m.end()]))
                key=None;expect=False
        elif depth==0:
            if t in ('=','?='):
                expect=key is not None
            elif expect:
                found.append((key,text[begin:m.end()]))
                key=None;expect=False
            else:
                key,begin=t,m.start()
    return found


@timed_often
def hollow(statement):
    if not statement.endswith('}'): return False
    rest=body(statement)
    parts=statements(rest)
    for _,part in parts: rest=rest.replace(part,'',1)
    return not rest.strip() and all(k=='limit' or hollow(part) for k,part in parts)


@timed_often
def branch(statement):
    found=selected(body(statement))
    return statement[:statement.index('{')]+'{\n'+found+'\n}',any(k!='limit' for k,_ in statements(found))


@timed_often
def selected(text):
    kept=[]
    chain=[]
    alive=False
    for key,statement in statements(text)+[(None,None)]:
        if key in CONTROL[1:]:
            made,found=branch(statement)
            chain.append(made)
            alive=alive or found
            continue
        if alive: kept+=chain
        chain=[]
        alive=False
        if key=='if':
            made,alive=branch(statement)
            chain=[made]
        elif key is not None and key not in DROPPED and not key.startswith('company:') and not hollow(statement):
            kept.append(statement)
    return '\n'.join(kept)


@timed
def copied(folder,tags):
    top=None
    found={}
    for path in sorted((GAME/'common/history'/folder).glob('*.txt')):
        for top,block in blocks(clean(path)):
            for key,inner in blocks(body(block)):
                if key[2:] in tags:
                    found[key[2:]]=selected(body(inner))
    return top,found


@timed
def kept(found,present,scripts,uses,stature):
    known={}
    return {tag:selected('\n'.join(checked(statement,present,scripts,known,stature) for key,statement in statements(stripped(text,stature))
                                   if valid(statement,present) and supported(key,statement,present,scripts,uses,known))) for tag,text in found.items()}


@timed
def stature():
    return {key for key,block in read(GAME,'common/static_modifiers') if STATURE.search(block)}


@timed_often
def carries(text,stature):
    opening=' '.join(inner for key,inner in blocks(body(text)) if key in ('immediate','modifiers_while_active'))
    return bool(SPENDING.search(opening) or set(NAME.findall(opening))&stature)


@timed_often
def stripped(text,stature):
    out=text
    for key,statement in statements(text):
        if key in SPENT or key=='add_modifier' and {a or b for a,b in MARKED.findall(statement)}&stature:
            out=out.replace(statement,'',1)
        elif statement.endswith('}'):
            inner=body(statement)
            cleaned=stripped(inner,stature)
            if cleaned!=inner: out=out.replace(statement,statement.replace(inner,cleaned,1),1)
    return out


@timed
def usage(vanilla,scripts):
    named={a or b for text in vanilla.values() for a,b in MARKED.findall(text)}
    return {name:[key for key,text in scripts.items() if text is not None and name in text] for name in named}


@timed_often
def supported(key,statement,present,scripts,uses,known):
    marked=[a or b for a,b in MARKED.findall(statement)] if key in ('add_modifier','set_variable') else []
    return all(not uses.get(name) or any(sound(k,present,scripts,known) for k in uses[name]) for name in marked)


@timed
def stationed(found,land,sea,templates):
    posted,admirals,_=templates
    out={}
    for tag,text in found.items():
        kept=[]
        for key,statement in statements(text):
            inner=body(statement) if statement.endswith('}') else None
            naval=key=='create_character' and (scalar(inner,'template') in admirals or scalar(inner,'is_admiral')=='yes')
            if naval and sea[tag] is None: continue
            if key=='create_character' and (scalar(inner,'template') in posted or scalar(inner,'hq')):
                statement='create_character = {\n'+re.sub(r'\bhq\s*=\s*\S+','',inner)+f'\nhq = sr:{sea[tag] if naval else land[tag]}\n}}'
            kept.append(statement)
        out[tag]='\n'.join(kept)
    return out


@timed
def templates():
    found=dict(read(GAME,'common/character_templates'))
    return ({key for key,block in found.items() if scalar(block,'hq')},{key for key,block in found.items() if scalar(block,'is_admiral')=='yes'},
            {key for key,block in found.items() if RULER.search(block)})


@timed_often
def ruled(text,templates):
    return bool(RULER.search(text)) or any(key in templates[2] for key in TEMPLATE.findall(text))


@timed
def names():
    return dict(re.findall(r'^ ([A-Z][A-Z0-9]{2}):\d* "([^"]*)"',(GAME/'localization/english/countries_l_english.yml').read_text(encoding='utf-8-sig'),re.M))


@timed
def everyone():
    return {key[2:]:selected(body(inner)) for _,top in read(GAME,'common/history/countries') for key,inner in blocks(body(top))}


@timed
def history(top,found):
    return f'{top} = {{\n'+'\n'.join(f'c:{tag} ?= {{\n{text}\n}}' for tag,text in found.items())+'\n}\n'


@timed
def laws():
    return {tag:set(found) for tag,found in json.loads(CALIBRATION.read_text(encoding='utf-8'))['laws'].items()}


@timed
def technologies(found):
    eras={}
    for key,block in read(GAME,'common/technology/technologies'):
        eras.setdefault(scalar(block,'era'),set()).add(key)
    effects=dict(read(GAME,'common/scripted_effects'))

    def expand(text):
        out=set(re.findall(r'add_technology_researched\s*=\s*(\w+)',text))
        for era in re.findall(r'add_era_researched\s*=\s*(\w+)',text): out|=eras[era]
        for name in re.findall(r'(effect_starting_technology_tier_\d+_tech)\s*=\s*yes',text): out|=expand(effects[name])
        return out
    return {tag:expand(text) for tag,text in found.items()}


@timed
def generic(folder):
    top=None
    kept=[]
    for path in sorted((GAME/'common/history'/folder).glob('*.txt')):
        for top,block in blocks(clean(path)):
            kept+=[inner for key,inner in blocks(body(block)) if not key.startswith(('c:','s:'))]
    return f'{top} = {{\n'+'\n'.join(kept)+'\n}\n'


@timed_often
def valid(text,present,pattern=REFERENCE):
    return not VANILLA_STATE.search(text) and set(pattern.findall(text))<=present


@timed
def scripts(stature):
    found=dict(read(GAME,'common/scripted_effects'))
    found.update(read(GAME,'common/scripted_triggers'))
    found.update((key,None if carries(text,stature) else text) for key,text in read(GAME,'common/journal_entries'))
    found.update((key,None if carries(text,stature) else text) for key,text in read(GAME,'events') if re.fullmatch(r'[\w-]+\.\d+',key))
    return found


@timed_often
def sound(key,present,scripts,known,seen=()):
    if scripts.get(key) is None: return False
    if key in seen: return True
    if key not in known:
        text=scripts[key]
        known[key]=valid(text,present,MENTION) and all(sound(name,present,scripts,known,seen+(key,)) for name in set(NAME.findall(text))&scripts.keys()-{key})
    return known[key]


@timed_often
def checked(text,present,scripts,known,stature):
    drop=lambda m:m[0] if sound(m[1] or m[2],present,scripts,known) else ''
    fire=lambda m:m[0] if sound(m[1] or m[2],present,scripts,known) and not offered(scripts[m[1] or m[2]],stature) else ''
    return EVENT.sub(fire,JOURNAL.sub(drop,text))


@timed_often
def offered(text,stature):
    options=' '.join(inner for key,inner in blocks(body(text)) if key=='option')
    return bool(SPENDING.search(options) or set(NAME.findall(options))&stature)


@timed
def sections(folder):
    found=[]
    for path in sorted((GAME/'common/history'/folder).glob('*.txt')):
        for top,block in blocks(clean(path)):
            found.append((top,statements(body(block))))
    return found


@timed
def conditional(found,present,scripts,stature):
    kept=[]
    known={}
    top=None
    for top,parts in found:
        for key,statement in parts:
            statement=stripped(statement,stature)
            if key.startswith('s:') or not valid(statement,present): continue
            if key=='add_contextless_journal_entry' and not sound(statement.split('=',1)[1].strip(),present,scripts,known): continue
            statement=checked(statement,present,scripts,known,stature)
            if key.startswith('c:'): statement=statement[:statement.index('{')]+'{\n'+selected(body(statement))+'\n}'
            if not hollow(statement): kept.append(statement)
    return f'{top} = {{\n'+'\n'.join(kept)+'\n}\n'


@timed_often
def cultures(block,text):
    found=set(re.search(r'cultures\s*=\s*\{([^}]*)\}',block)[1].split())
    for change,culture in CULTURE.findall(text):
        if change=='add': found.add(culture)
        else: found.discard(culture)
    return sorted(found)


@timed
def formables():
    definitions=dict(read(GAME,'common/country_definitions'))
    return [(tag,block,set(cultures(definitions[tag],'')),float(scalar(block,'required_states_fraction') or 1)) for tag,block in read(GAME,'common/country_formation')
            if scalar(block,'use_culture_states')=='yes' and tag in definitions]


@timed
def formations(found,homes,owner,totals):
    kept=[]
    capitals={}
    people={}
    for tag,block,wanted,fraction in found:
        homeland=[s for s,home in enumerate(homes) if home&wanted]
        if homeland and max(Counter(owner[s] for s in homeland).values())/len(homeland)<fraction:
            kept.append(block)
            capitals[tag]=max(homeland,key=lambda s:totals[s])
            people[tag]=sum(totals[s] for s in homeland)
    return '\n'.join(kept)+'\n',capitals,people
