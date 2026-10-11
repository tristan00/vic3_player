import logging
import time

from advisors.data.endgame import HISTORY, OBJECTIVE, scored_runs
from interface.common import timed
from . import ACTIVE, VERSION
from .data import training
from .features import selected_columns, selected_families, taxonomy
from .model import PickerModel
from .space import Space
from .storage import read

LOG=logging.getLogger('tuning')


@timed
def train(connection,model):
    started=time.monotonic()
    design=read(ACTIVE/f'{model}.json')
    groups=taxonomy(model)
    if design['version']!=VERSION or design['groups']!=groups or design['objective']!=OBJECTIVE:
        raise ValueError('Installed picker feature schema changed; retune before collecting')
    config=Space(groups).canonical(design['config'])
    bounds={run:(first,last,reason) for run,first,last,reason in connection.execute(HISTORY,scored_runs()).fetchall()}
    columns=selected_columns(groups,config)
    families=selected_families(groups,config) if model=='histogram' else None
    features,y,keys,weights=training(connection,bounds,model,columns,families=families)
    runs={key[0] for key in keys}
    loaded=time.monotonic()-started
    fitted=PickerModel(model,config,groups,design['threads']).fit(features,y,weights)
    duration=time.monotonic()-started-loaded
    LOG.info('%s trained %d rows, %d runs, %.2fs load, %.2fs fit',model,len(y),len(runs),loaded,duration)
    return fitted,len(y),len(set(map(tuple,keys))),len(runs),loaded,duration
