import argparse
import json
import logging
from pathlib import Path

import uvicorn

from .app import app

PORT=8790


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=PORT)
    parser.add_argument('--openapi',type=Path)
    arguments=parser.parse_args()
    if arguments.openapi:
        arguments.openapi.write_text(json.dumps(app.openapi(),indent=1),encoding='utf-8')
        return
    logging.basicConfig(level=logging.WARNING,format='%(asctime)s %(message)s')
    uvicorn.run(app,host='127.0.0.1',port=arguments.port,log_level='warning')


if __name__=='__main__':
    main()
