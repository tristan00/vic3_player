import random
from interface.common import timed_often

TIME_CONTROL={'pause','unpause','set_speed'}


class RandomAdvisor:
    name='random'

    @timed_often
    def __init__(self,seed=None,weights=None):
        self.random=random.Random(seed)
        self.base=weights or {}
        self.weights=dict(self.base)
        self.proposal=None

    @timed_often
    def start_run(self,store,actions,objective):
        self.weights={name:0 if self.base.get(name,1)==0 else 1 for name in actions}
        return self.weights

    @timed_often
    def choose(self,options):
        offered=sorted(name for name,combos in options.items() if combos and name not in TIME_CONTROL and self.weights.get(name,1)>0)
        if not offered:
            return None
        name=self.random.choices(offered,weights=[self.weights.get(name,1) for name in offered])[0]
        return name,self.random.choice(options[name])
