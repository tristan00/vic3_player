from functools import wraps
import json
import logging
import multiprocessing
from pathlib import Path
import time

DEFAULT_GAME=Path('D:/SteamLibrary/steamapps/common/Victoria 3')
DEFAULT_DATA=Path('D:/vic3_data/interface')


class GameCrashed(Exception):
    pass


def slot(value):
    return int(value)&0xffffff if int(value)!=-1 else -1


STALL_LIMIT=5
STEP_BYTES=200
PROGRESS_AT=multiprocessing.Value('d',time.monotonic(),lock=False)
PROGRESS_STEP=multiprocessing.Array('c',STEP_BYTES,lock=False)


def progress(step):
    PROGRESS_STEP.value=step.encode('utf-8','replace')[:STEP_BYTES-1]
    PROGRESS_AT.value=time.monotonic()


def read_progress(at,step):
    return step.value.decode('utf-8','replace'),time.monotonic()-at.value


def progress_age():
    return read_progress(PROGRESS_AT,PROGRESS_STEP)


def timed(method):
    @wraps(method)
    def call(*args,**kwargs):
        started=time.monotonic()
        progress(method.__qualname__)
        try:
            return method(*args,**kwargs)
        finally:
            progress(f'{method.__qualname__} done')
            logging.getLogger('interface').info('%s %.3fs',method.__name__,time.monotonic()-started)
    return call


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')


def write_script(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(value,encoding='utf-8-sig')
