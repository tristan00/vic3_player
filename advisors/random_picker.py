import random

TIME_CONTROL={'pause','unpause','set_speed'}
BACKLOG_WEEKS=52


def backlogged(snapshot):
    queue=snapshot.rows('player_construction_queue_item','construction_left,speed',private=False)
    return sum(left for left,_ in queue)>BACKLOG_WEEKS*sum(speed for _,speed in queue)


class RandomAdvisor:
    name='random'

    def __init__(self,seed=None,weights=None):
        self.random=random.Random(seed)
        self.weights=weights or {}

    def choose(self,options,snapshot):
        skipped={'build'} if options.get('build') and backlogged(snapshot) else set()
        offered=sorted(name for name,combos in options.items() if combos and name not in TIME_CONTROL|skipped and self.weights.get(name,1)>0)
        if not offered:
            return None
        name=self.random.choices(offered,weights=[self.weights.get(name,1) for name in offered])[0]
        return name,self.random.choice(options[name])
