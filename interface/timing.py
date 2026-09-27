from contextvars import ContextVar
from functools import wraps
import inspect
import logging
import math
from pathlib import Path
import threading
import time

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
        self.errors+=failed
        self.total+=ns
        self.own+=own
        self.low=ns if self.low is None else min(self.low,ns)
        self.high=max(self.high,ns)
        bucket=int(math.log2(max(ns,1))*RESOLUTION)
        self.buckets[bucket]=self.buckets.get(bucket,0)+1

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
            for kept in (self.whole,self.interval):
                if name not in kept:
                    kept[name]=Stats()
                kept[name].add(ns,own,failed)

    def merge(self,taken):
        with self.lock:
            for kept in (self.whole,self.interval):
                for name,stats in taken.items():
                    if name not in kept:
                        kept[name]=Stats()
                    kept[name].merge(stats)

    def take(self):
        with self.lock:
            taken,self.interval=self.interval,{}
        return taken

    def totals(self):
        with self.lock:
            return [(name,s.calls,s.errors,ms(s.total),ms(s.own),ms(s.low),ms(s.high),*(ms(s.quantile(share)) for share in QUANTILES))
                    for name,s in sorted(self.whole.items())]

    def drain(self):
        return [(name,s.calls,s.errors,ms(s.total),ms(s.own),ms(s.high)) for name,s in sorted(self.take().items())]


RECORDER=Recorder()


class Span:
    __slots__=('name','log','level','thread','parent','token','started','children','ns')

    def __init__(self,name,log,level=logging.INFO):
        self.name=name
        self.log=log
        self.level=level

    def __enter__(self):
        self.thread=threading.get_ident()
        self.children=0
        self.ns=None
        self.parent=OPEN.get()
        self.token=OPEN.set(self)
        self.started=time.perf_counter_ns()
        return self

    def __exit__(self,kind,error,traceback):
        self.ns=time.perf_counter_ns()-self.started
        OPEN.reset(self.token)
        if self.parent is not None and self.parent.thread==self.thread:
            self.parent.children+=self.ns
        RECORDER.add(self.name,self.ns,self.ns-self.children,kind is not None)
        trace=TRACE.get()
        if trace is not None:
            trace.append((self.name,ms(self.ns)))
        if kind is None:
            self.log.log(self.level,'%s %.1fms',self.name,ms(self.ns))
        else:
            self.log.log(self.level,'%s FAILED %s %.1fms',self.name,kind.__name__,ms(self.ns))

    @property
    def ms(self):
        return ms(time.perf_counter_ns()-self.started if self.ns is None else self.ns)

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
            raise TypeError(f'{function.__qualname__} is a generator or coroutine; timing the call would measure only its creation')
        name=span_name(function)
        if stamp is None:
            @wraps(function)
            def call(*args,**kwargs):
                with Span(name,logger,level):
                    return function(*args,**kwargs)
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
