from threading import Lock
import time

from miniworld.bank import status

from . import db, names

LOCK=Lock()
BANKS={}
FRESH=60


@db.often
def number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool)


@db.often
def flat(item,places):
    out={}
    for key,value in item.items():
        if isinstance(value,dict) and value and all(number(part) for part in value.values()):
            out[key+'_total']=sum(value.values())
        elif isinstance(value,(dict,list)):
            out[key+'_count']=len(value)
        else:
            out[key]=places.get(value,value) if isinstance(value,str) and key!='key' else value
    return out


@db.often
def scalars(known):
    return {**{key:value for key,value in known.items() if number(value)},
            **{name:value for part in known.values() if isinstance(part,dict) for name,value in part.items() if number(value)}}


@db.timed
def listing():
    found=db.records('''select w.world_id as world,max(r.world_file) as world_file,count(r.run_id) as runs,max(r.run_id) as last_run
        from world w left join run r using (world_id) group by 1 order by 1 desc''')
    for row in found:
        known=names.manifest(row['world'])
        if known:
            values=scalars(known)
            row.update(values,**{key+'_count':len(value) for key,value in known.items()
                                 if key not in values and isinstance(value,list) and value and all(isinstance(item,dict) for item in value)})
    return {'rows':found}


@db.timed
def bank(directory):
    with LOCK:
        found=BANKS.get(directory)
        if found is None or time.monotonic()-found[0]>FRESH:
            found=BANKS[directory]=(time.monotonic(),status(directory))
        return found[1]


@db.timed
def detail(world):
    if db.one('select 1 from world where world_id=%s',(world,)) is None:
        return None
    known=names.manifest(world)
    out={'world':world,'assets':db.records('select name,length(data) as bytes from world_asset where world_id=%s order by name',(world,)),
         'settings':{},'lists':{},'relations':[],'pacts':[],'map':None}
    if known is None:
        return out
    states=known['states']
    places={state['key']:state['name'] for state in states}
    out['settings']={**{key:value for key,value in known.items() if not isinstance(value,(list,dict))},**scalars(known)}
    out['settings'].update({key:', '.join(str(places.get(part,part)) for part in value) for key,value in known.items()
                            if isinstance(value,list) and value and not any(isinstance(part,(list,dict)) for part in value)})
    out['lists']={key:[flat(item,places) for item in value] for key,value in known.items() if isinstance(value,list) and value and all(isinstance(item,dict) for item in value)}
    out['map']={'provinces':{color:state['key'] for state in states for color in state['provinces']},
                'owners':{state['key']:state['country'] for state in states},'names':{state['key']:state['name'] for state in states}}
    out['relations']=[{'country':item['country'],'with':item['with'],'relations':item['value']} for item in known['relations']]
    out['pacts']=([{'country':item['overlord'],'with':item['subject'],'pact':item['type']} for item in known['subjects']]
                  +[{'country':item['country'],'with':item['rival'],'pact':'requested rivalry'} for item in known['rivals']])
    return out


@db.timed
def image(world,name):
    found=db.one("select data from world_asset where world_id=%s and name=%s and name like '%%.png'",(world,name))
    return bytes(found[0]) if found else None
