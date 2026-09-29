import argparse
from datetime import datetime, timezone
import re
import sys
import time

import psutil
import psycopg

from interface.common import DEFAULT_DATA
from interface.recording.store import DSN

POLL=.25
STATUS_EVERY=300
NO_RUN_LIMIT=420
GONE_GRACE=3
START_LIMIT=60
EVENT=re.compile(r'Traceback|CRITICAL|LATE FLAG|STALLED|CRASHED|REFUSED|WAS LOST|ROUND EXITED|^\{')
EXITED=re.compile(r'ROUND EXITED code=(\d+)')
FAILURE=re.compile(r'Traceback|CRITICAL|LATE FLAG|STALLED|CRASHED|REFUSED')


def say(text):
    print(f'{time.strftime("%H:%M:%S")} {text}',flush=True)


def events(lines):
    found=[]
    pending=False
    for line in lines:
        line=line.rstrip()
        if pending and line and not line[0].isspace():
            found.append(line)
            pending=False
        if EVENT.search(line):
            found.append(line)
            pending=line.startswith('Traceback')
    return found


def role(name,arguments):
    name=name.lower()
    arguments=[argument.replace('\\','/') for argument in arguments]
    if name=='python.exe' and any(argument.endswith('loop/supervise.py') for argument in arguments):
        return 'supervisor'
    if name=='cmd.exe' and any(argument.endswith('loop/launch.cmd') for argument in arguments):
        return 'round'
    if name=='python.exe' and 'loop.run' in arguments:
        return 'loop'
    if name=='victoria3.exe':
        return 'game'
    return None


def roles():
    return [(kind,process) for process in psutil.process_iter(['name','cmdline']) if (kind:=role(process.info['name'] or '',process.info['cmdline'] or []))]


def loop_processes():
    return [(process.info['name'].lower(),process.pid) for kind,process in roles() if kind in ('loop','game')]


class Watch:
    def __init__(self,name,since):
        self.name=name
        self.log=DEFAULT_DATA/f'{name}.log'
        self.since=since
        self.read=0
        self.connection=psycopg.connect(DSN,autocommit=True)
        self.runs={}
        self.flagged=set()
        self.failed=False
        self.gone_at=None
        self.seen=False
        self.status_at=time.monotonic()

    def log_events(self):
        if not self.log.exists():
            return []
        with open(self.log,encoding='utf-8',errors='replace') as handle:
            handle.seek(self.read)
            lines=handle.readlines()
            self.read=handle.tell()
        return events(lines)

    def run_events(self):
        for run_id,reason,detail,step,ms in self.connection.execute(
                'select run_id,end_reason,end_detail,longest_step,longest_step_ms from run where started_at>=%s order by run_id',(self.since,)):
            if run_id not in self.runs:
                say(f'RUN {run_id} opened')
                self.runs[run_id]=None
            if reason and self.runs[run_id] is None:
                self.runs[run_id]=reason
                say(f'RUN {run_id} ended {reason}'+(f': {detail}' if detail else '')+f'; longest step {step} {ms} ms')
                self.failed|=reason not in ('time','years','defeated')
        for run_id,step,silent in self.connection.execute('select run_id,progress_step,stalled_for from run_stalled'):
            if ('stalled',run_id) not in self.flagged:
                self.flagged.add(('stalled',run_id))
                say(f'RUN {run_id} STALLED in {step} for {silent.total_seconds():.1f} s')
                self.failed=True
        for run_id,silent in self.connection.execute('select run_id,silent_for from run_lost'):
            if ('lost',run_id) not in self.flagged:
                self.flagged.add(('lost',run_id))
                say(f'RUN {run_id} LOST: no heartbeat for {silent.total_seconds():.1f} s')
                self.failed=True

    def status(self):
        row=self.connection.execute('select run_id,progress_step,(select count(*) from snapshot s where s.run_id=r.run_id),'
                                    '(select count(*) from loop_action a where a.run_id=r.run_id) from run r where ended_at is null order by run_id desc limit 1').fetchone()
        say(f'RUNNING run={row[0]} step={row[1]} snapshots={row[2]} actions={row[3]}' if row else 'RUNNING, no open run')

    def finish(self,code):
        time.sleep(1)
        self.run_events()
        for name,pid in loop_processes():
            if name=='victoria3.exe':
                psutil.Process(pid).kill()
                say(f'GAME KILLED pid {pid}, it outlived the round')
        summary=', '.join(f'{run_id} {reason}' for run_id,reason in self.runs.items())
        say(f'ROUND {self.name} OVER code={code} runs: {summary or "none"}')
        return 0 if code==0 and not self.failed else 1

    def poll(self):
        for line in self.log_events():
            say(line)
            exited=EXITED.search(line)
            if exited:
                self.run_events()
                return self.finish(int(exited.group(1)))
            self.failed|=bool(FAILURE.search(line))
        self.run_events()
        alive=any(name=='python.exe' for name,_ in loop_processes())
        self.seen|=alive
        if not self.seen and (datetime.now(timezone.utc)-self.since).total_seconds()>START_LIMIT:
            say(f'LOOP PROCESS NEVER STARTED within {START_LIMIT} s')
            self.failed=True
            return self.finish(-1)
        if self.seen and not alive:
            self.gone_at=self.gone_at or time.monotonic()
            if time.monotonic()-self.gone_at>GONE_GRACE:
                say('LOOP PROCESS GONE without a ROUND EXITED line')
                self.failed=True
                return self.finish(-1)
        else:
            self.gone_at=None
        if not self.runs and (datetime.now(timezone.utc)-self.since).total_seconds()>NO_RUN_LIMIT and ('no_run',) not in self.flagged:
            self.flagged.add(('no_run',))
            say(f'NO RUN opened within {NO_RUN_LIMIT} s of the launch')
            self.failed=True
        if time.monotonic()-self.status_at>STATUS_EVERY:
            self.status_at=time.monotonic()
            self.status()
        return None

    def wait(self):
        while (code:=self.poll()) is None:
            time.sleep(POLL)
        return code


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('name')
    parser.add_argument('since',help='launch time, ISO 8601 UTC, as loop.launch printed it')
    arguments=parser.parse_args()
    sys.exit(Watch(arguments.name,datetime.fromisoformat(arguments.since)).wait())


if __name__=='__main__':
    main()
