from contextvars import ContextVar
from functools import wraps
import logging
import time

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from interface.recording.store import DSN

LOG=logging.getLogger('dashboard')
TRACE=ContextVar('trace',default=None)
POOL=None


def open_pool(dsn=DSN):
    global POOL
    POOL=ConnectionPool(dsn,min_size=2,max_size=8,kwargs={'autocommit':True,'row_factory':dict_row},open=True)
    return POOL


def close_pool():
    global POOL
    if POOL is not None:
        POOL.close()
        POOL=None


def rows(sql,params=()):
    with POOL.connection() as connection:
        return connection.execute(sql,params).fetchall()


def row(sql,params=()):
    with POOL.connection() as connection:
        return connection.execute(sql,params).fetchone()


def value(sql,params=()):
    found=row(sql,params)
    return None if found is None else next(iter(found.values()))


def timed(function):
    @wraps(function)
    def call(*args,**kwargs):
        started=time.perf_counter()
        try:
            return function(*args,**kwargs)
        finally:
            ms=(time.perf_counter()-started)*1000
            trace=TRACE.get()
            if trace is not None:
                trace.append((function.__name__,ms))
            LOG.info('%s %.1fms',function.__name__,ms)
    return call
