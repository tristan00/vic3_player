from interface.common import timed_often
from ..catalogue import LENGTHS


class RandomSizer:
    name='random'

    trained=None

    @timed_often
    def start_run(self,store,objective):
        pass

    @timed_often
    def size(self,snapshot,rng):
        return rng.choices(LENGTHS,weights=range(len(LENGTHS),0,-1))[0],None
