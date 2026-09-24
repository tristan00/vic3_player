from functools import wraps
import json
import logging
from pathlib import Path
import time

DEFAULT_GAME=Path('D:/SteamLibrary/steamapps/common/Victoria 3')
DEFAULT_DATA=Path('D:/vic3_data/interface')


class GameCrashed(Exception):
    pass


def slot(value):
    return int(value)&0xffffff if int(value)!=-1 else -1


STALL_LIMIT=5
PROGRESS={'step':'start','at':time.monotonic()}


def progress(step):
    PROGRESS.update(step=step,at=time.monotonic())


def progress_age():
    return PROGRESS['step'],time.monotonic()-PROGRESS['at']


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
