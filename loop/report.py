import collections
import json

from interface.actions.catalogue import ACTIONS
from interface.common import DEFAULT_DATA
from loop.coverage import COVERED, INFEASIBLE, ROWS
from loop.effects import EFFECTS, FLIPS

WARNINGS=('invalid','no_object','no_effect','ui_leftover')


def verifier(name):
    if name in EFFECTS:
        return 'none' if EFFECTS[name][1](None,None,{},None) is None else 'db'
    return 'flip' if name in FLIPS else 'missing'


def signal(name):
    try:
        return verifier(name)
    except (TypeError,AttributeError,KeyError):
        return 'db'


WAIVED={'set_speed':'the loop only ever sets speed 5, and run_days already checks that the clock ran and stopped near its target'}
MIN_VERIFIED=3
MIN_WORLDS=2
MIN_RATE=.95
TRAILING=3


def world_of(entry):
    return f"vanilla_{entry.get('tag')}" if entry.get('world')=='vanilla' else entry.get('world')


def coverage(paths):
    journals=collections.defaultdict(list)
    for path in paths:
        for line in path.read_text(encoding='utf-8').splitlines():
            entry=json.loads(line)
            seen=journals[entry['action']]
            if not seen or seen[-1][0]!=path.stem:
                seen.append((path.stem,[]))
            seen[-1][1].append(entry)
    counts=collections.defaultdict(collections.Counter)
    reasons=collections.defaultdict(collections.Counter)
    worlds=collections.defaultdict(set)
    for action,seen in journals.items():
        for _,entries in seen[-TRAILING:]:
            for entry in entries:
                counts[action][entry['status']]+=1
                if entry['status']=='verified':
                    worlds[action].add(world_of(entry))
                if entry['status'] in WARNINGS:
                    reasons[action][(entry['status'],entry.get('detail','')[:90])]+=1
    return counts,reasons,worlds


def main():
    paths=sorted((DEFAULT_DATA/'loop').glob('*.jsonl'))
    counts,reasons,worlds=coverage(paths)
    rows=[(action.name,signal(action.name),counts[action.name]) for action in ACTIONS]
    done=[name for name,kind,count in rows if name in WAIVED or (kind=='db' and count['verified']>=MIN_VERIFIED
          and len(worlds[name])>=MIN_WORLDS and count['verified']>=MIN_RATE*(count['verified']+sum(count[w] for w in WARNINGS)))]
    feasible=[row for row in ROWS if row not in INFEASIBLE]
    covered=[row for row in feasible if row in COVERED]
    print(f'coverage {len(covered)}/{len(feasible)} feasible catalogue rows ({len(INFEASIBLE)} infeasible), missing:')
    for row in feasible:
        if row not in COVERED:
            print(f'    {row:5s} {ROWS[row]}')
    print(f'verified {len(done)}/{len(rows)} actions by snapshot ({MIN_VERIFIED}+ times on {MIN_WORLDS}+ worlds, {MIN_RATE:.0%}+ of attempts, last {TRAILING} journals with the action), from {len(paths)} journals')
    print('unverified:',' '.join(sorted(name for name,_,_ in rows if name not in done)) or 'none')
    print('ui_leftover failures:',{name:count['ui_leftover'] for name,_,count in rows if count['ui_leftover']} or 'none')
    print('never attempted:',' '.join(name for name,_,count in rows if not sum(count.values())))
    for name,kind,count in sorted(rows,key=lambda row:(row[0] in done,-sum(row[2][w] for w in WARNINGS),row[0])):
        if name in done:
            continue
        print(f'{name:32s} {kind:8s} verified {count["verified"]:3d} unverified {count["unverified"]:3d} '
              +' '.join(f'{w} {count[w]:3d}' for w in WARNINGS)+(f' raced {count["raced"]:3d}' if count['raced'] else ''))
        for (status,detail),number in reasons[name].most_common(2):
            print(f'    {number:3d} {status} {detail}')


if __name__=='__main__':
    main()
