import collections
import re

from ..common import timed
from ..script import blocks, body, scalar
from .buildings import levels


@timed
def audit(states,files):
    pops={key.removeprefix('s:'):value for key,value in blocks(body(files['common/history/pops/interface.txt']))}
    buildings={key.removeprefix('s:'):value for key,value in blocks(body(files['common/history/buildings/interface.txt']))}
    totals=collections.Counter()
    rows=[]
    state_owners={s['key']:s['country'] for s in states}
    company_owners=set()
    company_errors=[]
    ownership_errors=[]
    duplicate_buildings=[]
    for country,record in blocks(body(files['common/history/countries/interface.txt'])):
        tag=country.removeprefix('c:')
        scopes=dict(blocks(body(record)))
        for company in re.findall(r'\badd_company\s*=\s*company_type:(\w+)',record):
            company_owners.add((company,tag))
            headquarters=scalar(scopes.get('company:'+company,''),'set_company_state_region')
            if headquarters is None or state_owners.get(headquarters.removeprefix('s:'))!=tag:
                company_errors.append(f'{company} in {tag}: missing or foreign headquarters')
    for _,record in blocks(body(files['common/history/buildings/interface.txt'])):
        for _,region in blocks(body(record)):
            seen=set()
            for _,building in blocks(body(region)):
                kind=scalar(building,'building')
                if kind in seen:
                    duplicate_buildings.append(kind)
                seen.add(kind)
                for key,ownership in blocks(body(building)):
                    if key=='add_ownership':
                        for kind,owner in blocks(body(ownership)):
                            if kind=='building' and state_owners.get(scalar(owner,'region'))!=(scalar(owner,'country') or '').removeprefix('c:'):
                                ownership_errors.append(owner)
                            if kind=='company' and (scalar(owner,'type'),(scalar(owner,'country') or '').removeprefix('c:')) not in company_owners:
                                company_errors.append(f'{scalar(owner,"type")}: ownership references an absent company')
    for state in states:
        source=state['source']
        expected_pops=' '.join(source['pop_records'])
        actual_pops=pops[state['key']]
        actual_buildings=buildings[state['key']]
        representatives={}
        for record in state['eligible_records']:
            kind=scalar(record,'building')
            if kind not in representatives or levels(record)>levels(representatives[kind]):
                representatives[kind]=record
        projected_methods=' '.join(representatives.values())
        numbers=lambda text,key:sum(int(n) for n in re.findall(r'\b'+key+r'\s*=\s*(\d+)',text))
        methods=lambda text:collections.Counter(m for value in re.findall(r'activate_production_methods\s*=\s*\{([^}]+)',text)
                                               for m in re.findall(r'\bpm_\w+',value))
        def types(text):
            result=collections.Counter()
            for _,record in blocks(text):
                if scalar(record,'size'):
                    key=' '.join(re.sub(r'\b(?:culture|size)\s*=\s*\w+','',record).split())
                    result[key]+=int(scalar(record,'size'))
            return result
        inner=' '.join(body(value) for _,value in blocks(body(actual_pops)))
        row={'state':state['key'],'source':source['key'],'source_population':numbers(expected_pops,'size'),
             'population':numbers(actual_pops,'size'),'excluded_levels':sum(r['levels'] for r in state['excluded_buildings'].values()),'source_levels':sum(levels(r) for r in source['building_records']),
             'levels':numbers(actual_buildings,'levels')+numbers(actual_buildings,'level'),'population_structure_preserved':types(expected_pops)==types(inner),
             'culture_projection_matches':collections.Counter(' '.join(r.split()) for _,r in blocks(inner))==collections.Counter(' '.join(r.split()) for r in state['pop_records']),
             'production_methods_match_projection':methods(projected_methods)==methods(actual_buildings),
             'source_arable':source['arable_land'],'arable':state['arable_land'],
             'source_coastal':source['coastal'],'coastal':state['coastal']}
        totals.update({key:row[key] for key in ('source_population','population','source_levels','levels','excluded_levels','source_arable','arable')})
        rows.append(row)
    return {'totals':dict(totals),'states':rows,
            'population_structure_preserved':all(r['population_structure_preserved'] for r in rows),
            'culture_projection_matches':all(r['culture_projection_matches'] for r in rows),
            'production_methods_match_projection':all(r['production_methods_match_projection'] for r in rows),
            'coast_mismatches':sum(r['source_coastal']!=r['coastal'] for r in rows),
            'coastal_templates_inland':sum(r['source_coastal'] and not r['coastal'] for r in rows),
            'companies':len(re.findall(r'\badd_company\s*=',files['common/history/countries/interface.txt'])),
            'company_errors':company_errors,'ownership_errors':ownership_errors,'duplicate_buildings':duplicate_buildings}
