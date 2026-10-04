import hashlib
from pathlib import Path
import time

import psutil

from interface.common import timed, timed_often
from .job import record
from .schema import GRAPH_VERSION


REGISTRY=Path(__file__).resolve().parents[3]/'artifacts'/'entity_graph_tracking'


class RunTracker:
    @timed
    def __init__(self,output,packed,configuration,attempts):
        output=output.resolve()
        output.mkdir(parents=True,exist_ok=True)
        process=psutil.Process()
        self.path=output/'tracking.json'
        self.data={'graph_version':GRAPH_VERSION,'output':str(output),'packed':str(packed.resolve()),
                   'started_at':time.time(),'pid':process.pid,'process_created':process.create_time(),
                   'configuration':configuration.mapping(),'attempts':list(dict.fromkeys(('full_world',*attempts))),
                   'state':'running','phase':'starting','completed_fits':0,'selected':None}
        self.update()
        REGISTRY.mkdir(parents=True,exist_ok=True)
        key=hashlib.sha256(str(output).encode()).hexdigest()[:20]
        record(REGISTRY/(key+'.json'),{'output':str(output)})

    @timed_often
    def update(self,**values):
        self.data.update(values,updated_at=time.time())
        record(self.path,self.data)


class FitTracker:
    @timed
    def __init__(self,output,name,configuration):
        output.mkdir(parents=True,exist_ok=True)
        process=psutil.Process()
        self.path=output/'status.json'
        self.data={'name':name,'graph_version':GRAPH_VERSION,'configuration':configuration.mapping(),
                   'state':'running','phase':'loading','started_at':time.time(),'epoch':0,
                   'epochs':configuration.epochs,'done':0,'total':0,'best_epoch':None,
                   'pid':process.pid,'process_created':process.create_time()}
        self.last=0.
        self.update()

    @timed_often
    def update(self,**values):
        self.data.update(values,updated_at=time.time())
        record(self.path,self.data)
        self.last=time.monotonic()

    @timed_often
    def advance(self,done,total):
        if done==total or time.monotonic()-self.last>=5:
            self.update(done=done,total=total)
