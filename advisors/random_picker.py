import random

TIME_CONTROL={'pause','unpause','set_speed'}
BACKLOG_WEEKS=52


def backlogged(snapshot):
    queue=snapshot.rows('player_construction_queue_item','construction_left,speed',private=False)
    return sum(left for left,_ in queue)>BACKLOG_WEEKS*sum(speed for _,speed in queue)


class RandomAdvisor:
    name='random'

    def __init__(self,seed=None,weights=None,param_weights=None):
        self.random=random.Random(seed)
        self.weights=weights or {}
        self.param_weights=param_weights or {}

    def combo_weight(self,name,combo):
        weight=1
        for param,values in self.param_weights.get(name,{}).items():
            weight*=values.get(combo.get(param),1)
        return weight

    def action_weight(self,name,combos):
        return self.weights.get(name,1)*sum(self.combo_weight(name,combo) for combo in combos)/len(combos)

    def choose(self,options,snapshot):
        skipped={'build'} if options.get('build') and backlogged(snapshot) else set()
        offered=sorted(name for name,combos in options.items() if combos and name not in TIME_CONTROL|skipped and self.action_weight(name,combos)>0)
        if not offered:
            return None
        name=self.random.choices(offered,weights=[self.action_weight(name,options[name]) for name in offered])[0]
        combos=options[name]
        return name,self.random.choices(combos,weights=[self.combo_weight(name,combo) for combo in combos])[0]
