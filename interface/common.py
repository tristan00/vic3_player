import json
import logging
from pathlib import Path

from .timing import timer

DEFAULT_GAME=Path('D:/SteamLibrary/steamapps/common/Victoria 3')
DEFAULT_DATA=Path('D:/vic3_data/interface')


class GameCrashed(Exception):
    pass


def slot(value):
    return int(value)&0xffffff if int(value)!=-1 else -1


def progress(step):
    logging.getLogger('interface').debug('%s',step)


timed=timer('interface')
timed_often=timer('interface',level=logging.DEBUG)


@timed_often
def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')


@timed_often
def write_script(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(value,encoding='utf-8-sig')
