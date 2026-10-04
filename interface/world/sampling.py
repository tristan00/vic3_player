from ..common import timed_often
from .generate import MAP


SLIDERS=('tech','ideology_uniformity','copies','tech_variation','country_economy','local_economy','source_regions','primary_culture_share')
SAMPLING={'tech':(.35,.65),'ideology_uniformity':(0,1),'copies':(0,1),'tech_variation':(.5,1.5),
          'country_economy':(.5,1.5),'local_economy':(.5,1.5),'source_regions':(1,4),'primary_culture_share':(0,1)}
PER_COUNTRY=('ideology_uniformity','primary_culture_share')


@timed_often
def world_size(rng,levels):
    states=rng.randint(*MAP['states'])
    low,high=MAP['country_share']
    return (rng.randrange(10**9),rng.randint(max(2,int(states*low)),max(2,int(states*high))),states,
            *[value if value is not None else SAMPLING[name] if name in PER_COUNTRY else
              rng.randint(*SAMPLING[name]) if name=='source_regions' else rng.uniform(*SAMPLING[name]) for name,value in zip(SLIDERS,levels)])
