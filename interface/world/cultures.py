import collections
import re

from ..common import timed
from ..script import scalar
from .source import integer_counts


@timed
def population(rng,data,states,primary,share):
    records=[(state,record) for state in states for record in state['source']['pop_records']]
    sizes=[int(scalar(record,'size')) for _,record in records]
    cultures=[scalar(record,'culture') for _,record in records]
    native=[culture in data['source_countries'][state['source']['owner']]['cultures']
            for (state,_),culture in zip(records,cultures)]
    total=sum(sizes)
    original=sum(size for size,own in zip(sizes,native) if own)
    target=round(share*total)
    if target>=original:
        counts=integer_counts([size if own else size*(target-original)/(total-original) if total!=original else 0
                               for size,own in zip(sizes,native)])
    else:
        counts=integer_counts([size*target/original if own else 0 for size,own in zip(sizes,native)])
    minorities=collections.Counter()
    for culture,size,own in zip(cultures,sizes,native):
        if not own and culture not in primary:
            minorities[culture]+=size
    if not minorities:
        minorities={culture:amount for culture,amount in data['culture_population'].items() if culture not in primary}
    primary_map={culture:primary[i%len(primary)] for i,culture in enumerate(sorted({culture for culture,own in zip(cultures,native) if own}))}
    for state in states:
        state['pop_records']=[]
        state['culture_map']={}
    for (state,record),culture,size,own,count in zip(records,cultures,sizes,native,counts):
        home=primary_map.get(culture) or rng.choice(primary)
        foreign=culture if not own and culture not in primary else rng.choices(list(minorities),list(minorities.values()))[0]
        for name,amount in ((home,count),(foreign,size-count)):
            if amount:
                changed=re.sub(r'\bculture\s*=\s*\w+',f'culture = {name}',record)
                changed=re.sub(r'\bsize\s*=\s*\d+',f'size = {amount}',changed)
                state['pop_records'].append(changed)
                state['culture_map'].setdefault(culture,set()).add(name)
    return target/total
