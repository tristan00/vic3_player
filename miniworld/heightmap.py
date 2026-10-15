import numpy as np
from PIL import Image

from interface.timing import evidence
from . import timed

TILE=64
SIZE=TILE+1
LEVELS=5


@timed
def pack(heights):
    rows,columns=heights.shape[0]//TILE,heights.shape[1]//TILE
    if heights.shape!=(rows*TILE,columns*TILE) or rows>256 or columns>256:
        raise ValueError(evidence(shape=heights.shape))
    up=np.pad(heights[::-1],((0,1),(0,1)),mode='edge')
    packed=np.zeros((rows*SIZE,columns*SIZE),np.uint16)
    indirection=np.zeros((rows,columns,4),np.uint8)
    for row in range(rows):
        for column in range(columns):
            packed[row*SIZE:(row+1)*SIZE,column*SIZE:(column+1)*SIZE]=up[row*TILE:row*TILE+SIZE,column*TILE:column*TILE+SIZE]
            indirection[row,column]=(column,row,1,0)
    end=rows*SIZE
    header=('heightmap_file="map_data/packed_heightmap.png"\nindirection_file="map_data/indirection_heightmap.png"\n'
            f'original_heightmap_size={{ {heights.shape[1]} {heights.shape[0]} }}\ntile_size={SIZE}\nshould_wrap_x=no\n'
            'level_offsets={ { 0 0 }'+f' {{ 0 {end} }}'*(LEVELS-1)+' }\n'
            f'max_compress_level={LEVELS-1}\nempty_tile_offset={{ 0 0 }}\n')
    return packed[::-1],indirection[::-1],header


@timed
def write(directory,heights):
    packed,indirection,header=pack(heights)
    Image.fromarray(heights.astype(np.uint16)).save(directory/'heightmap.png',compress_level=3)
    Image.fromarray(packed).save(directory/'packed_heightmap.png',compress_level=3)
    Image.fromarray(indirection,'RGBA').save(directory/'indirection_heightmap.png')
    (directory/'heightmap.heightmap').write_text(header,encoding='utf-8')
