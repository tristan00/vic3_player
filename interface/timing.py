from contextvars import ContextVar
from functools import wraps
import inspect
import logging
import math
from math import log2
from pathlib import Path
import sys
import threading
from threading import get_ident
import time
from time import perf_counter_ns

ROOT=Path(__file__).resolve().parents[1]
RESOLUTION=8
QUANTILES=(.5,.95,.99)
NS_PER_MS=1e6
INTERVAL_COLUMNS=('span','calls','errors','total_ms','self_ms','max_ms')
COLUMNS=('span','calls','errors','total_ms','self_ms','min_ms','max_ms','p50_ms','p95_ms','p99_ms')
OPEN=ContextVar('timing_open',default=None)
TRACE=ContextVar('timing_trace',default=None)


def ms(ns):
    return ns/NS_PER_MS


def evidence(**variables):
    frame=sys._getframe(1)
    return ' '.join([f'{frame.f_code.co_filename}:{frame.f_lineno}',frame.f_code.co_qualname,*(f'{name}={value!r}' for name,value in variables.items())])


class Stats:
    __slots__=('calls','errors','total','own','low','high','buckets')

    def __init__(self):
        self.calls=0
        self.errors=0
        self.total=0
        self.own=0
        self.low=None
        self.high=0
        self.buckets={}

    def add(self,ns,own,failed):
        self.calls+=1
        if failed:
            self.errors+=1
        self.total+=ns
        self.own+=own
        if self.low is None or ns<self.low:
            self.low=ns
        if ns>self.high:
            self.high=ns
        bucket=int(log2(ns)*RESOLUTION) if ns>1 else 0
        buckets=self.buckets
        buckets[bucket]=buckets.get(bucket,0)+1

    def merge(self,other):
        self.calls+=other.calls
        self.errors+=other.errors
        self.total+=other.total
        self.own+=other.own
        self.low=other.low if self.low is None else min(self.low,other.low)
        self.high=max(self.high,other.high)
        for bucket,count in other.buckets.items():
            self.buckets[bucket]=self.buckets.get(bucket,0)+count

    def quantile(self,share):
        rank=math.ceil(share*self.calls)
        seen=0
        for bucket in sorted(self.buckets):
            seen+=self.buckets[bucket]
            if seen>=rank:
                return min(max(2**((bucket+1)/RESOLUTION),self.low),self.high)


class Recorder:
    def __init__(self):
        self.lock=threading.Lock()
        self.whole={}
        self.interval={}

    def reset(self):
        with self.lock:
            self.whole={}
            self.interval={}

    def add(self,name,ns,own,failed):
        with self.lock:
            stats=self.interval.get(name)
            if stats is None:
                stats=self.interval[name]=Stats()
            stats.add(ns,own,failed)

    def merge(self,taken):
        with self.lock:
            fold(self.interval,taken)

    def take(self):
        with self.lock:
            taken,self.interval=self.interval,{}
            fold(self.whole,taken)
        return taken

    def totals(self):
        with self.lock:
            both={}
            fold(both,self.whole)
            fold(both,self.interval)
        return [(name,s.calls,s.errors,ms(s.total),ms(s.own),ms(s.low),ms(s.high),*(ms(s.quantile(share)) for share in QUANTILES))
                for name,s in sorted(both.items())]

    def drain(self):
        return [(name,s.calls,s.errors,ms(s.total),ms(s.own),ms(s.high)) for name,s in sorted(self.take().items())]


def fold(kept,taken):
    for name,stats in taken.items():
        if name not in kept:
            kept[name]=Stats()
        kept[name].merge(stats)


RECORDER=Recorder()


class Span:
    __slots__=('name','log','level','thread','parent','token','started','children','ns')

    def __init__(self,name,log,level=logging.INFO):
        self.name=name
        self.log=log
        self.level=level

    def __enter__(self):
        self.thread=get_ident()
        self.children=0
        self.ns=None
        self.parent=OPEN.get()
        self.token=OPEN.set(self)
        self.started=perf_counter_ns()
        return self

    def __exit__(self,kind,error,traceback):
        ns=self.ns=perf_counter_ns()-self.started
        OPEN.reset(self.token)
        parent=self.parent
        if parent is not None and parent.thread==self.thread:
            parent.children+=ns
        RECORDER.add(self.name,ns,ns-self.children,kind is not None)
        trace=TRACE.get()
        if trace is not None:
            trace.append((self.name,ms(ns)))
        log=self.log
        if log.isEnabledFor(self.level):
            if kind is None:
                log.log(self.level,'%s %.1fms',self.name,ms(ns))
            else:
                log.log(self.level,'%s FAILED %s %.1fms',self.name,kind.__name__,ms(ns))

    @property
    def ms(self):
        return ms(perf_counter_ns()-self.started if self.ns is None else self.ns)

    @property
    def seconds(self):
        return self.ms/1000


def span(name,log,level=logging.INFO):
    return Span(name,logging.getLogger(log),level)


def current():
    return OPEN.get()


def span_name(function):
    module='.'.join(Path(function.__code__.co_filename).resolve().relative_to(ROOT).with_suffix('').parts)
    return f'{module}.{function.__qualname__}'


def timer(log,stamp=None,level=logging.INFO):
    logger=logging.getLogger(log)

    def timed(function):
        if inspect.isgeneratorfunction(function) or inspect.iscoroutinefunction(function) or inspect.isasyncgenfunction(function):
            raise TypeError(evidence(function=function.__qualname__))
        name=span_name(function)
        if stamp is None:
            @wraps(function)
            def call(*args,**kwargs):
                timing=Span(name,logger,level)
                timing.__enter__()
                try:
                    result=function(*args,**kwargs)
                except BaseException as error:
                    timing.__exit__(type(error),error,None)
                    raise
                timing.__exit__(None,None,None)
                return result
            return call
        label=function.__qualname__
        done=f'{label} done'

        @wraps(function)
        def call(*args,**kwargs):
            stamp(label)
            try:
                with Span(name,logger,level):
                    return function(*args,**kwargs)
            finally:
                stamp(done)
        return call
    return timed
