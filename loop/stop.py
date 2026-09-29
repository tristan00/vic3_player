import psutil

from loop.watch import roles, say

ORDER=('supervisor','round','loop','game')


def main():
    found=sorted(roles(),key=lambda pair:ORDER.index(pair[0]))
    for kind,process in found:
        try:
            process.kill()
            say(f'KILLED {kind} pid {process.pid}')
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs([process for _,process in found],timeout=10)
    left=roles()
    say(f'STILL RUNNING {[(kind,process.pid) for kind,process in left]}' if left else 'STOPPED')


if __name__=='__main__':
    main()
