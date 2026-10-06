from ..common import timed_often
from .generate import MAP


SLIDERS=('tech','ideology_uniformity','copies','tech_variation','country_economy','local_economy','source_regions','primary_culture_share','military','interconnectedness')
SAMPLING={'tech':(.35,.5),'ideology_uniformity':(0,1),'copies':(1,1),'tech_variation':(.25,.75),
          'country_economy':(.8,1.2),'local_economy':(.8,1.2),'source_regions':(1,4),'primary_culture_share':(0,1),
          'military':(0,1),'interconnectedness':(0,1)}
PER_COUNTRY=('ideology_uniformity','primary_culture_share','country_economy')
PER_STATE=('local_economy',)


@timed_often
def world_size(rng,levels):
    states=rng.randint(*MAP['states'])
    low,high=MAP['country_share']
    return (rng.randrange(10**9),rng.randint(max(1,int(states*low)),max(1,int(states*high))),states,
            *[value if value is not None else SAMPLING[name] if name in PER_COUNTRY+PER_STATE else
              rng.randint(*SAMPLING[name]) if name=='source_regions' else rng.uniform(*SAMPLING[name]) for name,value in zip(SLIDERS,levels)])
