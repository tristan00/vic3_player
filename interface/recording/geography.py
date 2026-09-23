import hashlib
import io
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image

from ..common import timed
from ..script import read


def label(color):
    return f'x{int(color):06X}'


def normal(color):
    return 'x'+color[1:].upper()


def assets(root):
    return {entry.relative_to(root).as_posix():entry.read_bytes() for entry in sorted(root.rglob('*')) if entry.is_file()}


def identity(files,manifest=b''):
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    return hashlib.sha256(manifest+json.dumps(hashes,sort_keys=True,separators=(',',':')).encode('utf8')).hexdigest()


def mini_world(path):
    path=Path(path)
    raw=path.read_bytes()
    manifest=json.loads(raw)
    files=assets(Path(manifest['mod'])/'map_data')
    regions={normal(color):state['key'] for state in manifest['states'] for color in state['provinces']}
    return identity(files,raw),files,regions,{**files,'manifest.json':raw}


def vanilla_world(game):
    files=assets(Path(game)/'map_data')
    regions={}
    for key,value in read(Path(game),'map_data/state_regions'):
        for color in re.findall(r'x[0-9A-Fa-f]{6}',value.split('provinces',1)[1].split('}',1)[0]):
            if regions.setdefault(normal(color),key)!=key:
                raise RuntimeError(f'Province {color} belongs to state regions {regions[normal(color)]} and {key}')
    return identity(files),files,regions,files


@timed
def geometry(files,regions):
    terrain=files['province_terrains.txt'].decode('utf-8-sig')
    types={normal(color):kind for color,kind in re.findall(r'(x[0-9a-fA-F]{6})\s*=\s*"([^"]+)"',terrain)}
    with Image.open(io.BytesIO(files['provinces.png'])) as image:
        rgb=np.asarray(image.convert('RGB'),dtype=np.int32)
    pixels=(rgb[:,:,0]<<16)|(rgb[:,:,1]<<8)|rgb[:,:,2]
    colors,inverse,area=np.unique(pixels,return_inverse=True,return_counts=True)
    yy,xx=np.indices(pixels.shape)
    x=np.bincount(inverse.ravel(),weights=xx.ravel())/area
    y=np.bincount(inverse.ravel(),weights=yy.ravel())/area
    borders=[]
    for first,second in ((pixels[:,:-1],pixels[:,1:]),(pixels[:-1],pixels[1:])):
        unequal=first!=second
        first,second=first[unequal],second[unequal]
        borders.append((np.minimum(first,second).astype(np.int64)<<24)|np.maximum(first,second))
    edges,count=np.unique(np.concatenate(borders),return_counts=True)
    adjacencies=[{'first':label(edge>>24),'second':label(edge&0xffffff),'shared_border_pixels':int(n)} for edge,n in zip(edges,count)]
    provinces=[{'color':label(color),'region':regions.get(label(color)),'terrain':types.get(label(color)),'area_pixels':int(size),'x':float(cx),'y':float(cy)}
               for color,size,cx,cy in zip(colors,area,x,y)]
    return provinces,adjacencies
