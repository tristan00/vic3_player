from collections import defaultdict

from . import db
from .models import CountryProgress, CountryTrack, MarketGoods, MarketRow, Ref, Scope, TradePage, TradeSeries
from .names import game_date, labels, lookup

POINTS=240


def thin(seqs):
    if len(seqs)<=POINTS:
        return seqs
    step=(len(seqs)-1)/(POINTS-1)
    return sorted({seqs[round(i*step)] for i in range(POINTS)})


def changes(sql,run_id):
    by=defaultdict(list)
    for row in db.rows(sql,(run_id,)):
        by[row['seq']].append(row)
    return by


@db.timed
def country_progress(run_id):
    snapshots=db.rows('select seq,game_date from snapshot where run_id=%s order by seq',(run_id,))
    if not snapshots:
        return None
    player=db.value('select player_country from run where run_id=%s',(run_id,))
    states=changes('select seq,state,present,country from state_history where run_id=%s',run_id)
    provinces=changes('select seq,province,present,state from province_history where run_id=%s',run_id)
    people=changes('select seq,state,lower_strata+middle_strata+upper_strata as people from state_population where run_id=%s',run_id)
    economy=changes('select seq,country,present,gdp,total_exported_amount as exports,total_imported_amount as imports from country_economy_report where run_id=%s',run_id)
    alive=changes('select seq,country,present from country_history where run_id=%s',run_id)
    kept=set(thin([s['seq'] for s in snapshots]))
    owner,located,population,report,present={}, {}, {}, {}, set()
    tracks=defaultdict(lambda:{key:[] for key in ('states','provinces','population','gdp','exports','imports')})
    seqs,hours=[],[]
    for snap in snapshots:
        seq=snap['seq']
        for r in alive[seq]:
            (present.add if r['present'] else present.discard)(r['country'])
        for r in states[seq]:
            if r['present'] and r['country'] is not None:
                owner[r['state']]=r['country']
            else:
                owner.pop(r['state'],None)
        for r in provinces[seq]:
            if r['present'] and r['state'] is not None:
                located[r['province']]=r['state']
            else:
                located.pop(r['province'],None)
        for r in people[seq]:
            population[r['state']]=r['people']
        for r in economy[seq]:
            if r['present']:
                report[r['country']]=(r['gdp'],r['exports'],r['imports'])
            else:
                report.pop(r['country'],None)
        if seq not in kept:
            continue
        seqs.append(seq)
        hours.append(snap['game_date'])
        counts=defaultdict(lambda:[0,0,0])
        for state,country in owner.items():
            counts[country][0]+=1
            counts[country][2]+=population.get(state,0)
        for state in located.values():
            if state in owner:
                counts[owner[state]][1]+=1
        for country in present|set(tracks):
            track=tracks[country]
            here=country in present
            track['states'].append(counts[country][0] if here else None)
            track['provinces'].append(counts[country][1] if here else None)
            track['population'].append(float(counts[country][2]) if here else None)
            gdp,exports,imports=report.get(country,(None,None,None)) if here else (None,None,None)
            track['gdp'].append(gdp)
            track['exports'].append(exports)
            track['imports'].append(imports)
    width=len(seqs)
    names=labels(run_id,'country',list(tracks))
    countries=[]
    for country,track in tracks.items():
        padded={key:[None]*(width-len(values))+values for key,values in track.items()}
        countries.append(CountryTrack(ref=Ref(kind='country',id=country,label=names.get(country)),player=country==player,**padded))
    countries.sort(key=lambda c:(not c.player,-(next((v for v in reversed(c.gdp) if v is not None),0) or 0)))
    return CountryProgress(scope=Scope(text=f'every country of run {run_id}, replayed snapshot by snapshot',
                                       detail='states and provinces are those a country owns; population sums its states; gdp, exports and imports are the game reports; '
                                              f'{width} of {len(snapshots)} snapshots shown'),
                           seqs=seqs,hours=hours,countries=countries)


@db.timed
def trade_page(run_id,market,seq):
    last=db.value('select max(seq) from snapshot where run_id=%s',(run_id,))
    if last is None:
        return None
    seq=last if seq is None else min(seq,last)
    at=db.value('select game_date from snapshot where run_id=%s and seq=%s',(run_id,seq))
    markets=db.rows('''select m.market,m.owner,(select count(*) from (select distinct on (goods) present from market_goods g where g.run_id=%s and g.market=m.market and g.seq<=%s
                                                      order by goods,seq desc) x where present) as goods
                       from (select distinct on (market) market,owner,present from market_history where run_id=%s and seq<=%s order by market,seq desc) m where m.present''',
                    (run_id,seq,run_id,seq))
    player=db.value('select player_country from run where run_id=%s',(run_id,))
    mine=db.value('select market from country_history where run_id=%s and country=%s and seq<=%s and present order by seq desc limit 1',(run_id,player,seq))
    owners=labels(run_id,'country',[m['owner'] for m in markets])
    rows=[MarketRow(market=m['market'],owner=Ref(kind='country',id=m['owner'],label=owners.get(m['owner'])),goods=m['goods'],player=m['market']==mine) for m in markets]
    rows.sort(key=lambda r:(not r.player,-r.goods))
    chosen=market if market is not None else (rows[0].market if rows else None)
    goods=[]
    if chosen is not None:
        found=db.rows('''select goods,price,sell_orders,buy_orders from (select distinct on (goods) goods,present,price,sell_orders,buy_orders from market_goods
                         where run_id=%s and market=%s and seq<=%s order by goods,seq desc) x where present''',(run_id,chosen,seq))
        names=lookup('goods',[f['goods'] for f in found])
        ruleset=db.value('select ruleset_id from run where run_id=%s',(run_id,))
        costs={r['name']:float(r['value']) for r in db.rows("select name,value from game_definition where ruleset_id=%s and folder='common/goods' and field='cost'",(ruleset,))}
        for f in found:
            name=names[f['goods']]
            goods.append(MarketGoods(goods=name,price=f['price'],base=costs.get(name),sell=f['sell_orders'],buy=f['buy_orders']))
        goods.sort(key=lambda g:-(g.sell+g.buy))
    return TradePage(scope=Scope(text=f'markets of run {run_id} at snapshot {seq}',detail='sell orders are supply and buy orders demand, as the market reports them'),
                     seq=seq,game_date=game_date(at),markets=rows,market=chosen,goods=goods)


@db.timed
def trade_series(run_id,market,goods):
    code=db.value('select goods from goods where name=%s',(goods,))
    if code is None:
        return None
    found=db.rows('''select g.seq,s.game_date,g.present,g.price,g.sell_orders,g.buy_orders from market_goods g join snapshot s on s.run_id=g.run_id and s.seq=g.seq
                     where g.run_id=%s and g.market=%s and g.goods=%s order by g.seq''',(run_id,market,code))
    world=db.rows('select n,price from world_market_price_sample where run_id=%s and goods=%s order by n',(run_id,code))
    return TradeSeries(goods=goods,market=market,seqs=[f['seq'] for f in found],hours=[f['game_date'] for f in found],
                       price=[f['price'] if f['present'] else None for f in found],sell=[f['sell_orders'] if f['present'] else None for f in found],
                       buy=[f['buy_orders'] if f['present'] else None for f in found],world_n=[w['n'] for w in world],world_price=[w['price'] for w in world],
                       scope=Scope(text=f'{goods} in market {market} of run {run_id}',detail='values are stored when they change and hold until the next change'))
