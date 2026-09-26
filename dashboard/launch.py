import socket
import sys

from interface.runner.session import _spawn

from .server.__main__ import PORT


def main():
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',PORT))==0:
            print(f'REFUSED: something already listens on port {PORT}')
            sys.exit(2)
    process=_spawn(['cmd.exe','/c','D:/vic3_agent/dashboard/launch.cmd'],'D:/vic3_agent')
    print(f'LAUNCHED dashboard pid {process.pid} on http://127.0.0.1:{PORT}')


if __name__=='__main__':
    main()
