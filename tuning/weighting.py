from contextlib import contextmanager
import math
import msvcrt
import time

from interface.common import evidence, timed, timed_often
from .storage import read, write


class Conflict(ValueError):
    pass


@timed_often
def normalize(weights):
    if set(weights)!={'differentiation','reward'}:
        raise ValueError(evidence(weights=sorted(weights)))
    values={name:float(value) for name,value in weights.items()}
    if any(not math.isfinite(value) or value<0 for value in values.values()) or max(values.values())==0:
        raise ValueError(evidence(values=values))
    largest=max(values.values())
    scaled={name:value/largest for name,value in values.items()}
    total=sum(scaled.values())
    return {name:value/total for name,value in scaled.items()}


@contextmanager
def locked(directory):
    with (directory/'weighting.lock').open('a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_LOCK,1)
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)


@timed
def initialize(directory,weights):
    directory.mkdir(parents=True,exist_ok=True)
    with locked(directory):
        path=directory/'weighting.json'
        if path.exists():
            raise ValueError(evidence(path=path))
        state={'revision':0,'updated':time.time(),'weights':normalize(weights)}
        write(path,state)
    return state


@timed_often
def current(directory):
    state=read(directory/'weighting.json')
    normalize(state['weights'])
    if type(state['revision']) is not int or state['revision']<0 or not math.isfinite(state['updated']):
        raise ValueError(evidence(revision=state['revision'],updated=state['updated']))
    if not math.isclose(sum(state['weights'].values()),1.,rel_tol=0,abs_tol=1e-12):
        raise ValueError(evidence(weights=state['weights']))
    return state


@timed
def update(directory,revision,weights):
    values=normalize(weights)
    with locked(directory):
        previous=current(directory)
        if revision!=previous['revision']:
            raise Conflict(evidence(revision=revision,current=previous['revision']))
        state={'revision':revision+1,'updated':time.time(),'weights':values}
        write(directory/'weighting.json',state)
    return state
