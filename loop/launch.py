from datetime import datetime, timezone
import sys

from interface.common import DEFAULT_DATA
from interface.runner.session import _spawn
from loop.watch import Watch, loop_processes, say

LAUNCHER='D:/vic3_agent/loop/launch.cmd'


def main():
    name,*arguments=sys.argv[1:]
    running=loop_processes()
    if running:
        say(f'REFUSED: a round is still running {running}; kill it first')
        sys.exit(2)
    since=datetime.now(timezone.utc)
    (DEFAULT_DATA/f'{name}.log').unlink(missing_ok=True)
    process=_spawn(['cmd.exe','/c',LAUNCHER,name,*arguments],'D:/vic3_agent')
    say(f'LAUNCHED {name} {" ".join(arguments)} pid {process.pid} since {since.isoformat()}')
    sys.exit(Watch(name,since).wait())


if __name__=='__main__':
    main()
