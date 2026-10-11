import gzip
import hashlib
import json
from pathlib import Path
import pickle
import time
import uuid

from interface.common import timed, timed_often


@timed_often
def read(path):
    path=Path(path)
    for attempt in range(20):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except PermissionError:
            if attempt==19:
                raise
            time.sleep(.01)


@timed_often
def replace(temporary,path):
    for attempt in range(20):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt==19:
                raise
            time.sleep(.01)


@timed_often
def write(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')
    replace(temporary,path)


@timed
def save(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    with gzip.open(temporary,'wb',compresslevel=1) as stream:
        pickle.dump(value,stream,pickle.HIGHEST_PROTOCOL)
    replace(temporary,path)


@timed
def load(path):
    with gzip.open(path,'rb') as stream:
        return pickle.load(stream)


@timed
def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


@timed
def source_digest():
    root=Path(__file__).resolve().parents[1]
    files=sorted(path for directory in ('tuning','advisors','interface','loop') for path in (root/directory).rglob('*.py'))
    hasher=hashlib.sha256()
    for path in files:
        hasher.update(path.relative_to(root).as_posix().encode())
        hasher.update(path.read_bytes())
    return hasher.hexdigest()
