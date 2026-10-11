from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import logging
import math

import numpy
from psycopg_pool import ConnectionPool
from starlette.responses import Response

from advisors.data.rewards import HOURS_PER_YEAR
from interface.options.stored import YEAR_OFFSET, date_text
from interface.recording.store import DSN
from interface.timing import timer

CONNECTIONS=8
READY=10
timed=timer('dashboard')
often=timer('dashboard',level=logging.DEBUG)
POOL=ConnectionPool(DSN,min_size=1,max_size=CONNECTIONS,open=False,check=ConnectionPool.check_connection,
                    kwargs={'autocommit':True,'prepare_threshold':None,'options':'-c default_transaction_read_only=on'})


@timed
def open_pool():
    POOL.open(wait=True,timeout=READY)


@timed
def close_pool():
    POOL.close()


@often
def query(sql,params=()):
    with POOL.connection() as connection:
        cursor=connection.execute(sql,params)
        return [column.name for column in cursor.description],cursor.fetchall()


@often
def rows(sql,params=()):
    return query(sql,params)[1]


@often
def records(sql,params=()):
    columns,found=query(sql,params)
    return [dict(zip(columns,row)) for row in found]


@often
def one(sql,params=()):
    with POOL.connection() as connection:
        return connection.execute(sql,params).fetchone()


@often
def day(hours):
    if hours is None:
        return None
    year,month,number,_=date_text(hours).split('.')
    return f'{int(year):04d}-{int(month):02d}-{int(number):02d}'


@often
def year(hours):
    return hours/HOURS_PER_YEAR-YEAR_OFFSET


def plain(value):
    if value is None or isinstance(value,(str,bool,int)):
        return value
    if isinstance(value,float):
        return value if math.isfinite(value) else 'NaN' if value!=value else 'Infinity' if value>0 else '-Infinity'
    if isinstance(value,dict):
        return {key:plain(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):
        return [plain(item) for item in value]
    if isinstance(value,(set,frozenset)):
        return [plain(item) for item in sorted(value,key=str)]
    if isinstance(value,(datetime,date)):
        return value.isoformat()
    if isinstance(value,Decimal):
        return int(value) if value.is_finite() and value==value.to_integral_value() else plain(float(value))
    if isinstance(value,numpy.generic):
        return plain(value.item())
    if isinstance(value,(bytes,bytearray,memoryview)):
        return f'{memoryview(value).nbytes} bytes'
    if isinstance(value,timedelta):
        return str(value)
    raise TypeError(f'{type(value).__name__} has no JSON form')


@often
def reply(value,status=200,headers=None):
    return Response(json.dumps(plain(value),ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8'),status,headers,'application/json')
