from . import db, names

LEVELS='''with shots as (select seq from snapshot where run_id=%(run)s),
b as (select building,seq,coalesce(lead(seq) over (partition by building order by seq),2147483647) as until,present,building_type,state,levels,dead
      from building_history where run_id=%(run)s),
s as (select state,seq,coalesce(lead(seq) over (partition by state order by seq),2147483647) as until,present,country
      from state_history where run_id=%(run)s),
m as (select building,production_method,seq,coalesce(lead(seq) over (partition by building,production_method order by seq),2147483647) as until,present
      from building_production_method_active where run_id=%(run)s),
held as materialized (select t.seq,b.building,b.building_type,b.state,b.levels from shots t
      join b on b.seq<=t.seq and t.seq<b.until and b.present and not b.dead and b.levels>0
      join s on s.state=b.state and s.seq<=t.seq and t.seq<s.until and s.present and s.country=%(player)s)
select 'type',h.seq,k.name,null::int4,sum(h.levels)::int4 from held h join building_type k using (building_type) group by 2,3
union all select 'location',h.seq,null,h.state,sum(h.levels)::int4 from held h group by 2,4
union all select 'production_method',h.seq,p.name,null,sum(h.levels)::int4 from held h
      join m on m.building=h.building and m.seq<=h.seq and h.seq<m.until and m.present join production_method p using (production_method) group by 2,3'''
SHOTS='select seq,game_date from snapshot where run_id=%s order by seq'


@db.timed
def series(run):
    player=db.one('select player_country from run where run_id=%s',(run,))[0]
    shots=db.rows(SHOTS,(run,))
    position={seq:index for index,(seq,_) in enumerate(shots)}
    places=names.labels(run,'state')
    by={'type':{},'location':{},'production_method':{}}
    for view,seq,name,state,levels in db.rows(LEVELS,{'run':run,'player':player}):
        key=name if state is None else state
        entry=by[view].setdefault(key,{'name':name if state is None else places.get(state,str(state)),'state':state,'levels':[0]*len(shots)})
        entry['levels'][position[seq]]=levels
    return {'seqs':[seq for seq,_ in shots],'years':[db.year(date) for _,date in shots],'dates':[db.day(date) for _,date in shots],
            'by':{view:sorted(found.values(),key=lambda entry:entry['name']) for view,found in by.items()}}
