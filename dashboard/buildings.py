from interface.common import evidence

from . import db, names

HELD='''with shots as (select seq from snapshot where run_id=%(run)s),
b as (select building,seq,coalesce(lead(seq) over (partition by building order by seq),2147483647) as until,present,building_type,state,levels,dead
      from building_history where run_id=%(run)s),
s as (select state,seq,coalesce(lead(seq) over (partition by state order by seq),2147483647) as until,present,country
      from state_history where run_id=%(run)s),
m as (select a.building,p.name as production_method,a.seq,a.present,
             coalesce(lead(a.seq) over (partition by a.building,a.production_method order by a.seq),2147483647) as until
      from building_production_method_active a join production_method p using (production_method) where a.run_id=%(run)s),
held as materialized (select t.seq,b.building,k.name as type,b.state as location,b.levels from shots t
      join b on b.seq<=t.seq and t.seq<b.until and b.present and not b.dead and b.levels>0
      join building_type k using (building_type)
      join s on s.state=b.state and s.seq<=t.seq and t.seq<s.until and s.present and s.country=%(player)s)
'''
USING=' join m on m.building=h.building and m.seq<=h.seq and h.seq<m.until and m.present'
OPTIONS=HELD+'''select 'type',type,null::int4 from held group by 2
union all select 'location',null,location from held group by 3
union all select 'production_method',m.production_method,null from held h'''+USING+' group by 2'
SHOTS='select seq,game_date from snapshot where run_id=%s order by seq'
DIMENSIONS={'type':'h.type','location':'h.location','production_method':'m.production_method'}


@db.often
def narrowed(chosen,joined):
    wanted=[f'h.{name}=%({name})s' for name in ('type','location') if chosen[name] is not None]
    if chosen['production_method'] is not None:
        wanted.append('m.production_method=%(production_method)s' if joined else
                      'exists (select 1 from m where m.building=h.building and m.seq<=h.seq and h.seq<m.until and m.present and m.production_method=%(production_method)s)')
    return ' where '+' and '.join(wanted) if wanted else ''


@db.timed
def series(run,by,kind,location,method):
    by=by or ['type']
    if len(set(by))!=len(by) or not set(by)<=DIMENSIONS.keys():
        raise ValueError(evidence(by=by))
    chosen={'type':kind,'location':location,'production_method':method}
    params={'run':run,'player':db.one('select player_country from run where run_id=%s',(run,))[0],**chosen}
    shots=db.rows(SHOTS,(run,))
    position={seq:index for index,(seq,_) in enumerate(shots)}
    places=names.labels(run,'state')
    place=lambda state:{'id':state,'label':places.get(state,str(state))}
    options={name:[] for name in DIMENSIONS}
    for name,text,state in db.rows(OPTIONS,params):
        options[name].append(place(state) if name=='location' else text)
    total=[0]*len(shots)
    for seq,levels in db.rows(HELD+'select h.seq,sum(h.levels)::int4 from held h'+narrowed(chosen,False)+' group by 1',params):
        total[position[seq]]=levels
    joined='production_method' in by
    found={}
    for seq,*key,levels in db.rows(HELD+f'select h.seq,{",".join(DIMENSIONS[name] for name in by)},sum(h.levels)::int4 from held h'+(USING if joined else '')
                                   +narrowed(chosen,joined)+f' group by 1,{",".join(str(index+2) for index in range(len(by)))}',params):
        entry=found.setdefault(tuple(key),{**{name:place(value) if name=='location' else value for name,value in zip(by,key)},'levels':[0]*len(shots)})
        entry['levels'][position[seq]]=levels
    return {'seqs':[seq for seq,_ in shots],'years':[db.year(date) for _,date in shots],'dates':[db.day(date) for _,date in shots],'by':by,
            'options':{name:sorted(values,key=lambda value:value['label'] if name=='location' else value) for name,values in options.items()},
            'total':total,'rows':[found[key] for key in sorted(found,key=str)]}
