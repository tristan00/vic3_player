from types import SimpleNamespace
import re
import shutil
import struct

import numpy as np
from PIL import Image

from . import GAME, timed, timed_often

TEXTURES=('gfx/map/textures/colormap.dds','gfx/map/textures/flatmap.dds','gfx/map/textures/flatmap_overlay.dds','gfx/map/textures/colormap_tree.dds',
          'gfx/map/textures/land_mask.dds','gfx/map/water/watercolor_rgb_waterspec_a.dds',
          'gfx/map/water/flowmap.dds','gfx/map/water/foam_map.dds','gfx/map/dynamic_masks/exclusion_mask.dds','gfx/map/textures/windmap_tree.dds','gfx/models/papermap/flatmap.dds',
          'gfx/map/masks/mask_dynamic_farmland.png','gfx/map/masks/mask_dynamic_forestry.png','gfx/map/masks/mask_dynamic_mining.png')
THEMES='gfx/map/textures'
THEME='maptextures.settings'
TERRAIN='gfx/map/terrain'
OBJECTS='gfx/map/map_object_data'
LAYERS='layers.txt'
STRIDE=4
UNUSED=255

Image.MAX_IMAGE_PIXELS=None


@timed_often
def pixels(path,stride=1):
    with path.open('rb') as handle:
        header=handle.read(128)
        if path.suffix=='.dds' and header[84:88]==b'\0\0\0\0' and struct.unpack_from('<I',header,88)[0]==32:
            height,width=struct.unpack_from('<II',header,12)
            raw=np.fromfile(handle,np.uint32,width*height).reshape(height,width)[::stride,::stride]
            return np.stack([(raw&m)>>((m&-m).bit_length()-1) if m else np.full_like(raw,255) for m in struct.unpack_from('<4I',header,92)],2).astype(np.uint8)
    with Image.open(path) as image:
        values=np.asarray(image)[::stride,::stride]
    return values if values.ndim==3 else values[:,:,None]


@timed_often
def sampled(classes,shape):
    rows=np.arange(0,shape[0],STRIDE)*classes.shape[0]//shape[0]
    cols=np.arange(0,shape[1],STRIDE)*classes.shape[1]//shape[1]
    return classes[rows[:,None],cols[None,:]].ravel()


@timed
def profile(colors,inverse,shape,terrain,impassable):
    found=SimpleNamespace(kinds=sorted(set(terrain.values()))+['impassable'],means={},scales={},formats={})
    classes=np.array([found.kinds.index('impassable' if c in impassable else terrain[c]) for c in colors.tolist()],np.int8)[inverse].reshape(shape)
    size=len(found.kinds)
    for name in TEXTURES:
        values=pixels(GAME/name,STRIDE)
        with Image.open(GAME/name) as image:
            width,height=image.size
        at=sampled(classes,(height,width))
        counts=np.bincount(at,minlength=size)
        found.means[name]=np.stack([np.bincount(at,values[:,:,c].ravel().astype(float),size) for c in range(values.shape[2])],1)/counts[:,None]
        found.scales[name]=(height/shape[0],width/shape[1])
        with (GAME/name).open('rb') as handle:
            found.formats[name]='DXT1' if handle.read(88)[84:]==b'DXT1' else 'DXT5'
    index,intensity=(pixels(GAME/TERRAIN/f'detail_{part}.tga',STRIDE) for part in ('index','intensity'))
    with Image.open(GAME/TERRAIN/'detail_index.tga') as image:
        width,height=image.size
    at=sampled(classes,(height,width))
    weight=sum(np.bincount(at.astype(np.int64)*256+index[:,:,c].ravel(),intensity[:,:,c].ravel().astype(float),size*256) for c in range(4)).reshape(size,256)
    weight[:,UNUSED]=0
    found.material=weight.argmax(1).astype(np.uint8)
    found.masks=re.findall(r'mask\s*=\s*"(\w+)"',(GAME/TERRAIN/'materials.settings').read_text(encoding='utf-8-sig'))
    found.unlisted=sorted({p.stem for p in (GAME/TERRAIN).glob('mask_*.png')}-set(found.masks))
    found.themes=sorted({p.name for p in [*(GAME/THEMES).glob('maptextures*.settings'),*GAME.glob(f'dlc/*/{THEMES}/maptextures*.settings')]})
    return found


@timed_often
def save(path,values,mode,**options):
    path.parent.mkdir(parents=True,exist_ok=True)
    Image.fromarray(values,mode).save(path,**options)


@timed_often
def scaled(classes,factors):
    height,width=(max(4,-(-int(round(n*f))//4)*4) for n,f in zip(classes.shape,factors))
    return classes[(np.arange(height)*classes.shape[0]//height)[:,None],(np.arange(width)*classes.shape[1]//width)[None,:]]


@timed
def write(mod,world,found):
    classes=np.array([found.kinds.index('impassable' if p in world.impassable else world.terrain[p]) for p in range(world.count)],np.int8)[world.grid]
    sizes={factors:scaled(classes,factors) for factors in set(found.scales.values())}
    for name in TEXTURES:
        values=np.round(found.means[name]).astype(np.uint8)[sizes[found.scales[name]]]
        if name.endswith('.png'): save(mod/name,values[:,:,0],'L')
        else: save(mod/name,values,'RGBA',pixel_format=found.formats[name])
    material=found.material[np.repeat(np.repeat(classes,2,0),2,1)]
    index=np.full(material.shape+(4,),UNUSED,np.uint8)
    index[:,:,0]=material
    intensity=np.zeros(material.shape+(4,),np.uint8)
    intensity[:,:,0]=255
    save(mod/TERRAIN/'detail_index.tga',index,'RGBA',compression='tga_rle')
    save(mod/TERRAIN/'detail_intensity.tga',intensity,'RGBA',compression='tga_rle')
    used=set(found.material[np.unique(classes)].tolist())
    for position,mask in enumerate(found.masks):
        if position in used: save(mod/TERRAIN/f'{mask}.png',(material==position).astype(np.uint8)*255,'L')
    unused=[mask for position,mask in enumerate(found.masks) if position not in used]+found.unlisted
    if unused:
        empty=mod/TERRAIN/f'{unused[0]}.png'
        save(empty,np.zeros(material.shape,np.uint8),'L')
        for mask in unused[1:]: shutil.copyfile(empty,mod/TERRAIN/f'{mask}.png')
    for theme in found.themes:
        shutil.copyfile(GAME/THEMES/THEME,mod/THEMES/theme)
    (mod/OBJECTS).mkdir(parents=True,exist_ok=True)
    shutil.copyfile(GAME/OBJECTS/LAYERS,mod/OBJECTS/LAYERS)
