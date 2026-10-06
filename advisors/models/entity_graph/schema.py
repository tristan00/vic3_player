from dataclasses import asdict, dataclass

from interface.recording.spec import ENTITIES

from interface.common import timed_often
from ...catalogue import KEYS, RECORDED_PARAMS


OMIT={'name_key','first_name_key','last_name_key','localized_name_key','dynamic_name_key','dynamic_adjective_key',
      'map_color_override','color_red','color_green','color_blue','company_name_key','trends_initialized',
      'privatizable','recruitable','can_toll_straits','can_close_straits','has_bloc_mandates','historical',
      'current_location','target_location','target_other','invasion','power_bloc_map_texture'}
ENTITY_PARAMETERS={'military_formation':'formation',**{kind:kind for kind in ENTITIES if kind!='event' and kind not in KEYS}}
PARAMETERS={name:dict(params) for name,params in RECORDED_PARAMS.items()}
for action_parameters in PARAMETERS.values():
    if 'front' in action_parameters:
        action_parameters['front']='front'
HORIZONS=(90,180,365,730,1095)
COMPONENTS=('gdp','population','sol','stock')
GRAPH_VERSION=6


@dataclass(frozen=True)
class Design:
    name: str
    population: str='individual'
    goods: str='local'
    recurrence: bool=True
    scope: str='world'
    action_links: str='semantic'
    reverse: bool=True
    edges: bool=True
    geography: str='province'

    @timed_often
    def mapping(self):
        return asdict(self)


FULL_WORLD=Design('full_world')

