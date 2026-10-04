from datetime import datetime, timezone
import sys

from interface.runner.session import _spawn
from loop.run import main as run
from loop.supervise import LAUNCH, ROOT, next_round
from loop.watch import roles, say


def main():
    if '--no-supervisor' not in sys.argv[1:]:
        return run(sys.argv[1:])
    running=roles()
    if running:
        say(f'REFUSED: already running {[(kind,process.pid) for kind,process in running]}; stop it with python -m loop.stop')
        sys.exit(2)
    name=next_round()
    since=datetime.now(timezone.utc)
    process=_spawn(['cmd.exe','/c',str(LAUNCH),name,*sys.argv[1:]],str(ROOT))
    say(f'LAUNCHED {name} {" ".join(sys.argv[1:])} pid {process.pid}; follow it with python -m loop.watch {name} {since.isoformat()}')


if __name__=='__main__':
    main()
