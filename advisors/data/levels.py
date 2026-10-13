from bisect import bisect_right
import math

from interface.common import timed_often


class MeanLog:
    @timed_often
    def __init__(self,states):
        self.hours={}
        self.values={}
        self.totals={}
        for run,found in states.items():
            hours=sorted(found)
            totals=[0.]
            for first,last in zip(hours,hours[1:]):
                totals.append(totals[-1]+(last-first)*math.log1p(found[first]))
            self.hours[run]=hours
            self.values[run]=[found[hour] for hour in hours]
            self.totals[run]=totals

    @timed_often
    def mean_log(self,run,start,end):
        hours=self.hours.get(run,[])
        if end<=start or not hours or start<hours[0] or end>hours[-1]:
            return None
        values=[]
        for hour in (start,end):
            i=bisect_right(hours,hour)-1
            values.append(self.totals[run][i]+(hour-hours[i])*math.log1p(self.values[run][i]))
        return (values[1]-values[0])/(end-start)
