import logging

from interface.common import DEFAULT_GAME
from interface.timing import timer

GAME=DEFAULT_GAME/'game'
timed=timer('miniworld')
timed_often=timer('miniworld',level=logging.DEBUG)
