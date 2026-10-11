import random

from ..common import evidence, timed_often


SAMPLING={'random_ideology_share':(0,1),'copies':(1,1),'source_groups':(1,4),'primary_culture_share':(0,1),
          'military':(0,1),'interconnectedness':(0,1),'antagonism':(0,1),'war':(0,0),'sides':(0,0)}
SLIDERS=tuple(SAMPLING)
PER_COUNTRY=('random_ideology_share','primary_culture_share')
WHOLE=('source_groups','sides')


@timed_often
def room(states,pool):
    return states if pool is None else min(states,len(pool))


@timed_often
def jobs(settings):
    if set(settings['levels'])-set(SAMPLING):
        raise ValueError(evidence(unknown=sorted(set(settings['levels'])-set(SAMPLING))))
    rng=random.Random(settings['seed'])
    found={}
    while len(found)<settings['count']:
        job={'seed':rng.randrange(10**9),'states':rng.randint(*settings['states']),'countries':rng.randint(*settings['countries'])}
        groups=room(job['states'],settings['source_group_pool'])
        for name,(low,high) in SAMPLING.items():
            job[name]=[low,high] if name in PER_COUNTRY else rng.randint(low,min(high,groups)) if name in WHOLE else rng.uniform(low,high)
        job.update(settings['levels'])
        if not (1<=job['countries']<=room(job['states'],settings['country_pool']) and 0<=job['sides']<=job['countries'] and 1<=job['source_groups']<=groups and
                all(0<=low<=high<=1 for low,high in map(job.get,PER_COUNTRY)) and
                all(type(job[name]) is int if name in WHOLE else 0<=job[name]<=1 for name in SAMPLING if name not in PER_COUNTRY)):
            raise ValueError(evidence(job=job))
        found.setdefault(job['seed'],job)
    return list(found.values())
