from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from interface.recording.store import DSN
from interface.timing import timer

POOL=None
timed=timer('dashboard')


@timed
def open_pool(dsn=DSN):
    global POOL
    POOL=ConnectionPool(dsn,min_size=2,max_size=8,kwargs={'autocommit':True,'row_factory':dict_row},open=True)
    return POOL


@timed
def close_pool():
    global POOL
    if POOL is not None:
        POOL.close()
        POOL=None


@timed
def rows(sql,params=()):
    with POOL.connection() as connection:
        return connection.execute(sql,params).fetchall()


@timed
def row(sql,params=()):
    with POOL.connection() as connection:
        return connection.execute(sql,params).fetchone()


@timed
def value(sql,params=()):
    found=row(sql,params)
    return None if found is None else next(iter(found.values()))

