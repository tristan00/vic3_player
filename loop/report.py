import psycopg

from interface.recording.store import DSN
from loop.coverage import COVERED, INFEASIBLE, ROWS

FAILURES=('invalid','no_object','no_effect','ui_leftover')


def main():
    feasible=[row for row in ROWS if row not in INFEASIBLE]
    covered=[row for row in feasible if row in COVERED]
    print(f'coverage {len(covered)}/{len(feasible)} feasible catalogue rows ({len(INFEASIBLE)} infeasible), missing:')
    for row in feasible:
        if row not in COVERED:
            print(f'    {row:5s} {ROWS[row]}')
    with psycopg.connect(DSN) as c:
        verified,total,never=c.execute('select verified_actions,catalogue_actions,never_attempted from verification_summary').fetchone()
        runs=c.execute("select count(*),count(*) filter (where ended_at is not null) from run where kind<>'attached'").fetchone()
        print(f'verified {verified}/{total} actions by the database standard (3+ verified on 2+ worlds, 95%+ of attempts, last 3 runs with the action), '
              f'from {runs[0]} runs ({runs[1]} ended)')
        rows=c.execute('select action,runs,verified,unverified,failed,worlds from action_verification where not verified_by_standard order by failed desc,action').fetchall()
        print('unverified:',' '.join(sorted(name for name,*_ in rows)) or 'none')
        print('never attempted:',' '.join(sorted(name for name,count,*_ in rows if count==0)) or 'none')
        for name,count,good,pending,failed,worlds in rows:
            if count==0:
                continue
            print(f'{name:32s} runs {count:3d} verified {good:3d} unverified {pending:3d} failed {failed:3d} worlds {worlds}')
            for status,detail,number in c.execute(
                    "select status,left(coalesce(detail,''),90),count(*) from loop_action l join action a using (action) where a.name=%s and status=any(%s) "
                    "group by 1,2 order by 3 desc limit 2",(name,list(FAILURES))):
                print(f'    {number:3d} {status} {detail}')


if __name__=='__main__':
    main()
