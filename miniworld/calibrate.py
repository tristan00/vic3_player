import json
import logging
import shutil
import time
from pathlib import Path

import numpy as np

from interface.common import DEFAULT_DATA, slot, write_json
from interface.actions import Executor
from interface.runner.session import GameInterface
from . import bank, build, buildings, timed

OUT=Path(__file__).with_name('calibration.json')
WORLDS=20
SEED=7
MINIMUM=8
DAYS=14
FIELDS=('spending_bureaucracy_income','spending_bureaucracy_expenses','spending_authority_balance','spending_population_total')


@timed
def advance(game,days):
    executor=Executor(game)
    executor.run('set_speed',speed='4')
    executor.run('unpause')
    begin=game.reader().date()[0]
    while game.reader().date()[0]-begin<days*24: time.sleep(.5)
    executor.run('pause')
    time.sleep(1)


@timed
def measure(tag,manifest):
    game=GameInterface(profile='miniworld_calibration',quarterly_pause=False)
    try:
        game.campaign(tag,manifest)
        advance(game,DAYS)
        reader=game.reader()
        nations,_=reader.table('country')
        ai,_=reader.table('ai')
        laws,_=reader.table('law')
        tag_of={slot(i):reader.names[int(c)-1][1] for i,c in zip(nations['id'].tolist(),nations['country_definition'].tolist())}
        rows={tag_of[slot(c)]:dict(zip(FIELDS,values)) for c,*values in zip(ai['country'].tolist(),*(ai[f].tolist() for f in FIELDS))}
        active={}
        for country,law,on in zip(laws['country'].tolist(),laws['law'].tolist(),laws['active'].tolist()):
            if on: active.setdefault(tag_of[slot(country)],[]).append(reader.names[int(law)-1][1])
    finally:
        game.close()
    return rows,{tag:sorted(found) for tag,found in active.items()}


@timed
def generated(directory):
    models=build.prepare()
    rng=np.random.default_rng(SEED)
    rows=[]
    for index in range(WORLDS):
        knobs={**bank.draw(rng),'diplomacy':0.,'ideology':0.}
        knobs['countries']=max(knobs['countries'],min(MINIMUM,knobs['states']))
        out=directory/f'world_{index}'
        made=build.build(models,out,int(rng.integers(2**31)),knobs)
        measured,_=measure(next(iter(made.owned)),str(out/'manifest.json'))
        for tag,members in made.owned.items():
            rows.append({'tag':tag,'pops':[made.totals[s] for s in members],'incorporated':sum(s not in made.unincorporated for s in members),'invested':buildings.invested(models.administration,made.copied[tag],models.laws[tag]),
                         'commanders':buildings.commanders(models.administration,made.characters.get(tag,'')),'expenses':measured[tag]['spending_bureaucracy_expenses']})
        shutil.rmtree(out)
    return rows


@timed
def calibrate():
    rows,laws=measure('GBR',None)
    write_json(OUT,{'vanilla':rows,'laws':laws,'generated':[]})
    rows=generated(DEFAULT_DATA.parent/'miniworld'/'calibration')
    write_json(OUT,{**json.loads(OUT.read_text(encoding='utf-8')),'generated':rows})


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    calibrate()
