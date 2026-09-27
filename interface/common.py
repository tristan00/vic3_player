import json
import logging
import multiprocessing
from pathlib import Path
import time

from .timing import timer

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
PROGRESS_VERSION=multiprocessing.Value('q',0,lock=False)
READ_ATTEMPTS=1000


def progress(step):
    PROGRESS_VERSION.value+=1
    PROGRESS_STEP.value=step.encode('utf-8','replace')[:STEP_BYTES-1]
    PROGRESS_AT.value=time.monotonic()
    PROGRESS_VERSION.value+=1


def read_progress(version,at,step):
    for _ in range(READ_ATTEMPTS):
        before=version.value
        if before%2:
            continue
        name,stamp=step.value,at.value
        if version.value==before:
            return name.decode('utf-8'),time.monotonic()-stamp
    return None


def progress_age():
    while (read:=read_progress(PROGRESS_VERSION,PROGRESS_AT,PROGRESS_STEP)) is None:
        time.sleep(0)
    return read


timed=timer('interface',progress)
timed_often=timer('interface',level=logging.DEBUG)


@timed_often
def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')


@timed_often
def write_script(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(value,encoding='utf-8-sig')
