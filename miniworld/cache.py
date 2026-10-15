import hashlib
import os
import pickle
import sys
from pathlib import Path

import numpy
import PIL
import scipy

from interface.common import DEFAULT_DATA
from . import GAME, timed

CACHE=DEFAULT_DATA/'miniworld_models.pickle'


@timed
def revision():
    local=Path(__file__).parent
    sources=[*local.glob('*.py'),local/'calibration.json',local.parent/'interface/script.py']
    files=[GAME/'localization/english/countries_l_english.yml',*GAME.glob('dlc/*/gfx/map/textures/maptextures*.settings')]
    for folder in ('common','events','map_data','gfx/map','gfx/models/papermap'):
        files.extend(path for path in (GAME/folder).rglob('*') if path.is_file())
    digest=hashlib.sha256(repr((sys.version,numpy.__version__,scipy.__version__,PIL.__version__)).encode())
    for path in sorted(sources):
        digest.update(str(path).encode())
        digest.update(path.read_bytes())
    for path in sorted(files):
        stat=path.stat()
        digest.update(repr((str(path),stat.st_mtime_ns,stat.st_size)).encode())
    return digest.digest()


@timed
def prepared(make):
    signature=revision()
    if CACHE.exists():
        with CACHE.open('rb') as handle:
            previous=pickle.load(handle)
            if previous==signature: return pickle.load(handle)
    found=make()
    CACHE.parent.mkdir(parents=True,exist_ok=True)
    pending=CACHE.with_suffix(f'.{os.getpid()}.tmp')
    with pending.open('wb') as handle:
        pickle.dump(signature,handle,protocol=pickle.HIGHEST_PROTOCOL)
        pickle.dump(found,handle,protocol=pickle.HIGHEST_PROTOCOL)
    pending.replace(CACHE)
    return found
