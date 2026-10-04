import argparse
import logging

from ..common import DEFAULT_DATA, DEFAULT_GAME, timed
from .generate import generate


@timed
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--seed',type=int,required=True)
    parser.add_argument('--countries',type=int,default=6)
    parser.add_argument('--states',type=int,default=30)
    parser.add_argument('--tech',type=float,default=.5)
    parser.add_argument('--ideology-uniformity',type=float,default=0)
    parser.add_argument('--primary-culture-share',type=float)
    parser.add_argument('--copies',type=float,default=0)
    parser.add_argument('--tech-variation',type=float,default=1)
    parser.add_argument('--country-economy',type=float,default=1)
    parser.add_argument('--local-economy',type=float,default=1)
    parser.add_argument('--source-regions',type=int,default=1)
    parser.add_argument('--region-keys',nargs='+')
    parser.add_argument('--game-dir',default=str(DEFAULT_GAME))
    parser.add_argument('--data-dir',default=str(DEFAULT_DATA))
    arguments=vars(parser.parse_args())
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    print(generate(**arguments))


if __name__=='__main__':
    main()
