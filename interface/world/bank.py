import json
import msvcrt
from pathlib import Path
from uuid import uuid4

from ..common import DEFAULT_GAME, timed, timed_often
from .cache import checked, configure, launch, publish, status, worlds


class Bank:
    @timed_often
    def __init__(self,directory):
        self.directory=Path(directory).resolve()
        self.path=self.directory/'bank.json'

    @timed_often
    def outputs(self):
        return sorted({Path(path) for path in json.loads(self.path.read_text(encoding='utf-8'))['outputs']})

    @timed
    def add(self,output):
        self.directory.mkdir(parents=True,exist_ok=True)
        with open(self.directory/'bank.lock','a+b') as lock:
            lock.seek(0)
            msvcrt.locking(lock.fileno(),msvcrt.LK_LOCK,1)
            known=self.outputs() if self.path.exists() else []
            publish(self.path,{'outputs':sorted({str(path) for path in [*known,output]})})

    @timed
    def take(self,rng):
        available=[path for output in self.outputs() for path in worlds(output)]
        if not available:
            raise ValueError('Bank has no completed worlds')
        path=rng.choice(available)
        checked(path)
        return path

    @timed
    def append(self,count,countries,states=(10,30),workers=20,seed=None,game=DEFAULT_GAME,source_group_pool=None,country_pool=None,**levels):
        output=self.directory/'outputs'/uuid4().hex
        configure(output,count=count,countries=countries,states=states,levels=levels,seed=seed,game=game,source_group_pool=source_group_pool,country_pool=country_pool)
        result=launch(output,workers)
        self.add(output)
        return result

    @timed
    def status(self):
        outputs=[{'output':str(output),'worlds':len(worlds(output)),'status':status(output)} for output in self.outputs()]
        return {'worlds':sum(output['worlds'] for output in outputs),'outputs':outputs}
