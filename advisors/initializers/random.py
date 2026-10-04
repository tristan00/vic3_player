import random
from interface.common import timed_often

LOW,HIGH=-2.,2.


class RandomAdvisor:
    name='random'

    @timed_often
    def __init__(self,seed=None,weights=None):
        self.random=random.Random(seed)
        self.excluded={name for name,weight in (weights or {}).items() if weight==0}
        self.weights={}
        self.proposal=None

    @timed_often
    def start_run(self,store,actions,objective):
        self.weights={name:0 if name in self.excluded else 10**self.random.uniform(LOW,HIGH) for name in actions}
        return self.weights
