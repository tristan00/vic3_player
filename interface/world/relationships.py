import collections

from ..common import slot, timed


@timed
def loaded(reader,manifest):
    tables={key:reader.table(key)[0] for key in ('country','state','building','building_ownership','company','formation','hq','combat_unit')}
    label=lambda token:reader.names[int(token)-1][1] if token else None
    countries=tables['country']
    tags={slot(ident):label(kind) for ident,kind in zip(countries['id'],countries['country_definition'])}
    states=tables['state']
    locations={slot(ident):(slot(country),label(region)) for ident,country,region in zip(states['id'],states['country'],states['state_region'])}
    buildings=tables['building']
    building_states={slot(ident):slot(state) for ident,state in zip(buildings['id'],buildings['state'])}
    errors=[]
    for ident,capital in zip(countries['id'],countries['capital']):
        if locations.get(slot(capital),(None,None))[0]!=slot(ident):
            errors.append(f'{tags[slot(ident)]}: missing or foreign capital')
    ownership=tables['building_ownership']
    for ident,kind,owner,building in zip(ownership['id'],ownership['identity_type'],ownership['identity_building'],ownership['building']):
        if slot(building) not in building_states or (int(kind)==1 and slot(owner) not in building_states) or (int(kind)==2 and slot(owner) not in tags):
            errors.append(f'Ownership {slot(ident)}: dangling owner or building')
    companies=tables['company']
    for ident,country,building,region in zip(companies['id'],companies['country'],companies['building'],companies['state_region']):
        home=(slot(country),label(region))
        if home not in locations.values() or (slot(building)!=-1 and locations.get(building_states.get(slot(building)))!=home):
            errors.append(f'Company {slot(ident)}: headquarters disagrees with country or state')
    hqs=tables['hq']
    headquarters={slot(ident):(slot(country),label(group)) for ident,country,group in zip(hqs['id'],hqs['country'],hqs['hq_region'])}
    group_states={r['key']:set(r['states']) for r in manifest['groups']}
    formations=tables['formation']
    formation_countries={slot(ident):slot(country) for ident,country in zip(formations['id'],formations['country'])}
    for ident,country,hq in zip(formations['id'],formations['country'],formations['home_hq']):
        owner,group=headquarters.get(slot(hq),(None,None))
        if owner!=slot(country) or not any(c==owner and state in group_states.get(group,set()) for c,state in locations.values()):
            errors.append(f'Formation {slot(ident)}: missing or foreign headquarters')
    units=tables['combat_unit']
    counts=collections.Counter()
    for ident,country,building,formation in zip(units['id'],units['country'],units['building'],units['formation']):
        location=locations.get(building_states.get(slot(building)))
        if location is None or location[0]!=slot(country) or formation_countries.get(slot(formation))!=slot(country):
            errors.append(f'Unit {slot(ident)}: missing or foreign building or formation')
        else:
            counts[tags[location[0]],location[1]]+=1
    for state in manifest['states']:
        if counts[state['country'],state['key']]!=state['buildings'].get('building_barrack',0):
            errors.append(f'{state["key"]}: units do not match barracks levels')
    return {'errors':errors,'countries':len(tags),'companies':len(companies['id']),
            'formations':len(formation_countries),'units':len(units['id']),'ownerships':len(ownership['id'])}
