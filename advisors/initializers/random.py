import json
import random
from pathlib import Path
from statistics import NormalDist

from interface.common import evidence, timed_often
from ..catalogue import NAMES

LOW,HIGH=-2.,2.
DRAW=json.loads((Path(__file__).parent/'centres.json').read_text(encoding='utf-8'))
CENTRE,SPREAD,CENTRES=DRAW['default'],DRAW['spread'],DRAW['centres']
if set(CENTRES)-set(NAMES) or not all(LOW<=centre<=HIGH for centre in (CENTRE,*CENTRES.values())) or SPREAD<=0:
    raise ValueError(evidence(unknown=sorted(set(CENTRES)-set(NAMES)),centre=CENTRE,centres=CENTRES,spread=SPREAD,low=LOW,high=HIGH))


class RandomAdvisor:
    name='random'

    @timed_often
    def __init__(self,seed=None,weights=None):
        self.random=random.Random(seed)
        self.excluded={name for name,weight in (weights or {}).items() if weight==0}
        self.weights={}
        self.used={}
        self.proposal=None

    @timed_often
    def start_run(self,store,actions,objective,kept):
        self.used={name:CENTRES.get(name,CENTRE) for name in actions if name not in self.excluded}
        self.weights={name:10**self.around(self.used[name]) if name in self.used else 0 for name in actions}

    @timed_often
    def candidates(self,names,count):
        self.used={name:CENTRES.get(name,CENTRE) for name in names}
        return [[self.around(centre) for centre in self.used.values()] for _ in range(count)]

    @timed_often
    def around(self,centre):
        bell=NormalDist(centre,SPREAD)
        return min(HIGH,max(LOW,bell.inv_cdf(self.random.uniform(bell.cdf(LOW),bell.cdf(HIGH)))))
