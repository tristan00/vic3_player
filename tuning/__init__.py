from pathlib import Path

from interface.common import DEFAULT_DATA

ROOT=DEFAULT_DATA.parent/'tuning'/'pickers'
VERSION=1
ACTIVE=Path(__file__).with_name('active')
RANDOM_TRIALS=40
