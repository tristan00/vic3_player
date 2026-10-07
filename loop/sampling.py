from advisors.catalogue import ANSWERS, LEVER, PROPOSALS
from interface.common import timed, timed_often
from interface.options import available
from .conflicts import context, cost, invalidates, resources, targets
from .translate import offer

FINISH={'capitulate','back_down','white_peace','declare_bankruptcy','leave_power_bloc'}


@timed_often
def block_length(rng):
    return rng.choices(range(6,17),weights=range(11,0,-1))[0]


class Sampler:
    @timed
    def __init__(self,snapshot,advisor):
        self.random=advisor.random
        self.weights={'answer_event':1,**advisor.weights}
        offered=offer(snapshot,available(snapshot))
        links=context(snapshot)
        self.budget=resources(snapshot)
        questions=[[('answer_event',c) for c in offered.get('answer_event',[]) if c.params['event']==event]
                   for event in sorted({c.params['event'] for c in offered.get('answer_event',[])})]
        questions+=[[(n,c) for n in pair for c in offered.get(n,[]) if c.params['country']==country]
                    for pair in PROPOSALS for country in sorted({c.params['country'] for n in pair for c in offered.get(n,[])})]
        regular=[(n,c) for n,items in offered.items() if n not in ANSWERS and n!='abandon_law_enactment' for c in items]
        self.pools=[[(n,c,command,targets(*command,links),invalidates(*command,links),cost(snapshot,*command))
                     for n,c in group if self.weights[LEVER[n]]>0 for command in c.commands]
                    for group in [*questions,regular]]

    @timed_often
    def block(self,length):
        if length<1:
            raise ValueError('Block length must be positive')
        block,claimed,budget=[],set(),self.budget.copy()
        pools=[pool[:] for pool in self.pools]
        question=0
        for position in range(length):
            for index in range(question,len(pools)):
                pools[index]=[item for item in pools[index] if not item[3]&claimed
                              and all(value<=budget[key] for key,value in item[5].items())]
            while question<len(pools)-1 and not pools[question]:
                question+=1
            live=[item for item in pools[question] if position==length-1 or item[2][0] not in FINISH]
            if not live:
                raise RuntimeError(f'No selectable action for slot {position+1} of {length}')
            levers=sorted({LEVER[item[0]] for item in live})
            lever=self.random.choices(levers,weights=[self.weights[name] for name in levers])[0]
            name=self.random.choice(sorted({item[0] for item in live if LEVER[item[0]]==lever}))
            choice=self.random.choice(list({id(item[1]):item[1] for item in live if item[0]==name}.values()))
            item=self.random.choice([item for item in live if item[0]==name and item[1] is choice])
            block.append((name,choice.params,item[2]))
            claimed.update(item[4])
            for key,value in item[5].items():
                budget[key]-=value
            if question<len(pools)-1:
                question+=1
        return block


@timed
def batches(snapshot,advisor,count,length=None):
    sampler=Sampler(snapshot,advisor)
    return [sampler.block(block_length(advisor.random) if length is None else length) for _ in range(count)]
