import numpy as np
from scipy.stats import norm, rankdata

from interface.common import timed, timed_often
from .endgame import rewards

WEIGHTS='''select w.run_id,a.name,w.weight from run_weight w join advisor_action a on a.advisor_action=w.advisor_action where w.run_id = any(%s)
and (select count(*) from run_advisor ra where ra.run_id=w.run_id)=1'''


@timed_often
def normalized(y):
    return norm.ppf((rankdata(y)-.5)/len(y))


@timed
def history(connection,space):
    scored=rewards(connection)
    weights={}
    for run_id,action,weight in connection.execute(WEIGHTS,(list(scored),)).fetchall():
        weights.setdefault(run_id,{})[action]=weight
    runs=[run_id for run_id in scored if all(weights.get(run_id,{}).get(action,0)>0 for action in space)]
    X=np.array([[np.log10(weights[run_id][action]) for action in space] for run_id in runs])
    return X.reshape(len(runs),len(space)),np.array([scored[run_id] for run_id in runs]),runs


