import argparse
import logging
from pathlib import Path

from . import timed
from .build import build, prepare


@timed
def main():
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('out',type=Path)
    parser.add_argument('--seed',type=int,required=True)
    parser.add_argument('--states',type=int,default=30)
    parser.add_argument('--countries',type=int,default=6)
    parser.add_argument('--concentration',type=float,default=1.)
    parser.add_argument('--landmasses',type=int,default=1)
    parser.add_argument('--climate',type=float,default=.5)
    parser.add_argument('--relief',type=float,default=1.)
    parser.add_argument('--density',type=float,default=1.)
    parser.add_argument('--diversity',type=float,default=1.)
    parser.add_argument('--diplomacy',type=float,default=.5)
    parser.add_argument('--ideology',type=float,default=0.)
    args=vars(parser.parse_args())
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    out,seed=args.pop('out'),args.pop('seed')
    args['size']=args['states']/args['countries']
    build(prepare(),out,seed,args)


if __name__=='__main__':
    main()
