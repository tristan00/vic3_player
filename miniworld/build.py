from types import SimpleNamespace
import numpy as np

from interface.timing import evidence
from . import buildings, companies, countries, diplomacy, economy, geography, ideology, military, regions, states, textures, timed, write
from .cache import prepared


@timed
def prepare():
    return prepared(model)


@timed
def model():
    found=SimpleNamespace()
    found.geography=geography.profile()
    people=countries.populations()
    found.economy=economy.templates(people)
    found.known=countries.candidates()
    vanilla=countries.everyone()
    found.density=states.model(vanilla)
    found.administration=buildings.administration(people)
    found.laws=countries.laws()
    found.methods=buildings.methods(countries.technologies(vanilla),found.laws)
    found.military=military.model(people)
    found.companies=companies.model()
    found.diplomacy=diplomacy.model()
    found.ideology=ideology.scripts()
    found.generic={folder:countries.generic(folder) for folder in countries.GENERIC}
    found.conditional={folder:countries.sections(folder) for folder in countries.CONDITIONAL}
    found.stature=countries.stature()
    found.scripts=countries.scripts(found.stature)
    found.uses=countries.usage(vanilla,found.scripts)
    found.templates=countries.templates()
    found.names=countries.names()
    found.formables=countries.formables()
    found.tiers=countries.tiers(people)
    found.wealth=countries.wealth(found.known,vanilla)
    return found


@timed
def build(models,out,seed,knobs):
    if not (1<=knobs['countries']<=knobs['states'] and 1<=knobs['landmasses']<=knobs['states']): raise ValueError(evidence(knobs=knobs))
    rng=np.random.default_rng(seed)
    world=geography.generate(rng,models.geography,knobs)
    described=regions.describe(rng,models.economy.templates.keys(),models.geography,world)
    tags=countries.pick(rng,models.known,knobs['countries'])
    history={folder:countries.copied(folder,set(tags)) for folder in countries.COPIED}
    history['countries']=history['countries'][0],countries.kept(history['countries'][1],set(tags),models.scripts,models.uses,models.stature)
    copied=history['countries'][1]
    techs=countries.technologies(copied)
    laws={tag:models.laws[tag] for tag in tags}
    owned,home,component=states.settle(world,described,states.owners(rng,world,described,tags,knobs['concentration']))
    owner={s:tag for tag,members in owned.items() for s in members}
    totals,furnished=economy.furnish(rng,models.economy,described,owner,techs,knobs['density'])
    capitals=states.capitals(rng,models.density,owned,totals,home,component)
    economy.harbours(models.economy,furnished,described,owned,capitals,component,totals,laws)
    unincorporated=states.unincorporated(rng,models.density,world,owned,capitals)
    population={tag:sum(totals[s] for s in members) for tag,members in owned.items()}
    tiers=countries.tiered(rng,models.tiers,population)
    region_of={s:f'region_mw_{index+1}' for index,members in enumerate(world.regions) for s in members}
    formations,fleets=military.history(rng,models.military,described,owned,totals,capitals,region_of,techs)
    top,found=history['characters']
    shores={tag:[s for s in sorted(members,key=lambda s:s!=capitals[tag]) if 'port' in described[s]['hubs']] for tag,members in owned.items()}
    history['characters']=top,countries.stationed(found,{tag:region_of[s] for tag,s in capitals.items()},
                                                  {tag:region_of[coast[0]] if tag in fleets else None for tag,coast in shores.items()},models.templates)
    history.update({folder:(top,countries.kept(found,set(tags),models.scripts,models.uses,models.stature)) for folder,(top,found) in history.items() if folder!='countries'})
    ruled={tag for tag,text in history['characters'][1].items() if countries.ruled(text,models.templates)}
    cultures={tag:countries.cultures(models.known[tag],copied[tag]) for tag in tags}
    mixes=states.mix(rng,models.density,world,owner,cultures,totals,knobs['diversity'])
    homes=states.homelands(rng,models.density,mixes)
    formables,founded,homeland=countries.formations(models.formables,homes,owner,totals)
    keys={tag:described[s]['key'] for tag,s in {**founded,**capitals}.items()}
    ranked={**countries.tiered(rng,models.tiers,{tag:n for tag,n in homeland.items() if tag not in tiers}),**tiers}
    admin=buildings.administer(rng,models.administration,models.methods,owned,totals,techs,laws,copied,history['characters'][1],unincorporated)
    built,placed=buildings.history(rng,models.economy.owners,models.methods,described,owner,furnished,techs,laws,admin)
    history['countries']=history['countries'][0],companies.found_companies(rng,models.companies,owned,placed,described,copied)
    relations=diplomacy.arrange(rng,models.diplomacy,world,owned,population,knobs['diplomacy'],laws,ruled,tiers)
    mod=out/'mod'
    write.reset(mod)
    write.images(mod,world)
    textures.write(mod,world,models.geography.textures)
    write.graphics(mod,world,described)
    write.map_text(mod,world,described)
    labels=dict(world.labels)
    pacts,rivalries,goals,blocs=diplomacy.history(relations,models.names,labels)
    write.localization(mod,labels)
    for name,content in countries.definitions(keys,ranked).items():
        write.text(mod/'common/country_definitions'/name,content)
    for folder,(top,found) in history.items():
        write.text(mod/f'common/history/{folder}/miniworld.txt',countries.history(top,found))
    for folder,content in models.generic.items():
        write.text(mod/f'common/history/{folder}/miniworld.txt',content)
    for folder,found in models.conditional.items():
        write.text(mod/f'common/history/{folder}/miniworld.txt',countries.conditional(found,set(tags),models.scripts,models.stature))
    write.text(mod/'common/history/ai/miniworld_goals.txt',goals)
    write.text(mod/'common/history/diplomacy/miniworld.txt',pacts)
    write.text(mod/'common/history/power_blocs/miniworld.txt',blocs)
    write.text(mod/'common/scripted_triggers/miniworld_ideology.txt',models.ideology[0])
    write.text(mod/'common/scripted_effects/miniworld_ideology.txt',models.ideology[1])
    write.text(mod/'common/on_actions/miniworld.txt','on_game_started = {\n\ton_actions = { mw_shuffle_ideologies }\n}\non_game_started_after_lobby = {\n\ton_actions = { mw_rivalries }\n}\n'
               +ideology.started(knobs['ideology'])+rivalries)
    write.text(mod/'common/history/population/miniworld.txt',countries.population(rng,models.wealth,{tag:techs[tag] for tag in tags}))
    write.text(mod/'common/history/states/miniworld.txt',states.history(world,described,owned,homes,write.color,unincorporated,states.claims(rng,models.density,owned,homes,cultures)))
    write.text(mod/'common/country_formation/miniworld.txt',formables)
    write.text(mod/'common/history/pops/miniworld.txt',states.pops(rng,models.density,described,owner,mixes))
    write.text(mod/'common/history/buildings/miniworld.txt',built)
    write.text(mod/'common/history/military_formations/miniworld.txt',formations)
    write.metadata(mod,write.FIXED+[textures.OBJECTS,'common/country_creation','common/country_formation']
                   +[f'common/history/{folder}' for folder in countries.COPIED+countries.REPLACED])
    result=SimpleNamespace()
    result.world,result.described,result.owned,result.totals,result.copied,result.laws,result.admin=world,described,owned,totals,copied,laws,admin
    result.characters=history['characters'][1]
    result.unincorporated=unincorporated
    write.manifest(out,mod,seed,knobs,world,described,owned,totals,capitals,labels,models.names,relations,tiers)
    return result
