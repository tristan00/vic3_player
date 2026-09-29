from datetime import datetime, timezone
import sys

from interface.runner.session import _spawn
from loop.supervise import next_round
from loop.watch import loop_processes, say

LAUNCHER='D:/vic3_agent/loop/launch.cmd'


def main():
    running=loop_processes()
    if running:
        say(f'REFUSED: a round is still running {running}; stop it with python -m loop.stop')
        sys.exit(2)
    name=next_round()
    since=datetime.now(timezone.utc)
    process=_spawn(['cmd.exe','/c',LAUNCHER,name,*sys.argv[1:]],'D:/vic3_agent')
    say(f'LAUNCHED {name} {" ".join(sys.argv[1:])} pid {process.pid}; follow it with python -m loop.watch {name} {since.isoformat()}')


if __name__=='__main__':
    main()
