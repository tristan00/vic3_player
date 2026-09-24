from datetime import datetime, timezone
import time
import unittest

import psycopg

from interface.options.stored import Stored
from interface.recording.store import Store, install
from interface.recording.spec import TABLES
from interface.recording.tables import Built

DSN='host=127.0.0.1 port=55433 dbname=vic3_test user=postgres'
GEN=1<<24
PLAYER=1|GEN
OTHER=2|GEN
STATE=5|GEN
BUILDING=9
LAW=11
GROUP=13
PROVINCE=21
MEMBERS={'common/country_definitions':['AAA','BBB'],'common/laws':['law_one','law_two'],'map_data/state_regions':['STATE_TEST'],'common/terrain':['plains'],
         'common/buildings':['building_farm'],'common/interest_groups':['ig_test'],'common/government_types':['gov_test'],'common/religions':['faith']}
ENUMS={'approval_state':{0:'angry'},'influence_type':{0:'influential'},'influence_type_reason':{0:'above_influential_threshold'}}


def filler(column):
    return None if column.optional or column.entity else {'bool':False,'float8':0.0}.get(column.kind,0)


def empty():
    rows={table.name:[] for table in TABLES}
    for table in TABLES:
        if table.kind=='singleton':
            rows[table.name]=[tuple(filler(column) for column in table.columns)]
    return rows


def country(ident,definition,capital):
    return (ident,definition,'gov_test','faith',None,None,-1,capital,-1,-1,-1,-1,-1,None,None,False,True,False,None,None)


def built(step):
    rows=empty()
    rows['country_history']=[country(PLAYER,'AAA',STATE),country(OTHER,'BBB',-1)]
    rows['state_private']=[(STATE,1.5)]
    rows['state_history']=[(STATE,'STATE_TEST','Hometown',PLAYER,-1,-1,-1,False)]
    rows['province_history']=[(PROVINCE,STATE,PLAYER)]
    rows['law_history']=[(LAW,PLAYER,'law_one',step['progress'],1,None,True,-1)]+([(LAW+1,PLAYER,'law_two',0.0,1,None,False,-1)] if step['second'] else [])
    rows['interest_group_history']=[(GROUP,PLAYER,'ig_test','ig_name',-1,-1,0,0,True,0)]
    rows['interest_group_clout_sample']=[(GROUP,n,100*n if n==step['head'] else None,value) for n,value in step['samples']]
    return Built(rows,{'player_country':PLAYER,'game_speed':1,'first_start':True,'custom_rng_seed':'seed','game_rules':[]},
                 {'game_date':1000+step['head'],'local_date_time':0,'paused':None,'speed':None,'ui_panel_open':False,'ui_interaction_open':False,
                  'ui_map_list_open':False},{PROVINCE:1})


STEPS=[{'progress':0.1,'second':True,'head':1,'samples':[(1,0.5)]},
       {'progress':0.2,'second':True,'head':2,'samples':[(1,0.5),(2,0.6)]},
       {'progress':0.2,'second':False,'head':2,'samples':[(2,0.6)]}]


class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            connection=psycopg.connect(DSN,autocommit=True)
        except psycopg.OperationalError as error:
            raise unittest.SkipTest(f'test database unavailable: {error}')
        install(connection)
        connection.close()

    def setUp(self):
        self.store=Store(DSN)
        self.store.ruleset(b'rules',{folder:list(names) for folder,names in {**{f:[] for f in self.folders()},**MEMBERS}.items()},[],[],[],[],[],ENUMS,
                             [('income',1,'income_taxes')])
        self.store.world('ab',[{'color':'x000001','region':'STATE_TEST','terrain':'plains','area_pixels':4,'x':1.0,'y':2.0}],[],{})
        self.store.session='test'
        self.store.begin_run(started_at=datetime(2026,9,23,tzinfo=timezone.utc),kind='attached')

    def tearDown(self):
        if self.store.run_id is not None:
            self.store.connection.execute('select delete_run(%s)',(self.store.run_id,))
        self.store.connection.close()

    def folders(self):
        from interface.recording.spec import VOCABULARIES
        return {folder for folders in VOCABULARIES.values() if folders for folder in folders}

    def write_all(self):
        for step in STEPS:
            self.store.write(built(step),'post_action',datetime(2026,9,23,tzinfo=timezone.utc),1.0)

    def test_versions_tombstones_and_query_layer(self):
        self.write_all()
        c=self.store.connection
        run=self.store.run_id
        self.assertEqual(c.execute('select seq,present,progress from law_history where run_id=%s and law=%s order by seq',(run,LAW)).fetchall(),
                         [(0,True,0.1),(1,True,0.2)])
        self.assertEqual(c.execute('select seq,present from law_history where run_id=%s and law=%s order by seq',(run,LAW+1)).fetchall(),
                         [(0,True),(2,False)])
        self.assertEqual(c.execute('select law,progress from law_at(%s,2) order by law',(run,)).fetchall(),[(LAW,0.2)])
        self.assertEqual(c.execute('select law from law_at(%s,1) order by law',(run,)).fetchall(),[(LAW,),(LAW+1,)])
        self.assertEqual(c.execute('select state,seq,wage from state_private_at(%s,2)',(run,)).fetchall(),[(STATE,0,1.5)])
        self.assertEqual(c.execute('select n,seq,date,clout from interest_group_clout_sample where run_id=%s order by n',(run,)).fetchall(),
                         [(1,0,100,0.5),(2,1,200,0.6)])
        self.assertEqual(c.execute('select province,color from province where run_id=%s',(run,)).fetchall(),[(PROVINCE,1)])
        self.assertEqual(c.execute("select l.name from law_history h join law_type l using (law_type) where run_id=%s and law=%s limit 1",(run,LAW)).fetchone(),
                         ('law_one',))
        stored=Stored(c,run,2)
        self.assertEqual(stored.rows('law','law,law_type',country=PLAYER),[(LAW,'law_one')])
        self.assertEqual(stored.states(),[STATE])

    def test_a_handle_keeps_its_identity_and_anchors_it_even_without_the_object(self):
        early=built(STEPS[0])
        early.rows['front_history']=[(3,1.0,2.0)]
        early.rows['front_side_history']=[(4,3,6,0)]
        early.rows['law_history'][0]=(LAW,PLAYER&0xffffff,'law_one',0.1,1,None,True,-1)
        self.store.write(early,'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        c=self.store.connection
        run=self.store.run_id
        self.assertEqual(c.execute('select war,first_seq from war where run_id=%s',(run,)).fetchall(),[(6,0)])
        self.assertEqual(c.execute('select count(*) from war_history where run_id=%s',(run,)).fetchone(),(0,))
        self.assertEqual(c.execute('select front,war from front_side_at(%s,0)',(run,)).fetchall(),[(3,6)])
        self.assertEqual(c.execute('select country from law_at(%s,0) where law=%s',(run,LAW)).fetchall(),[(PLAYER&0xffffff,)])
        self.assertEqual(c.execute('select entity,identity from referenced_only where run_id=%s order by entity',(run,)).fetchall(),
                         [('country',PLAYER&0xffffff),('war',6)])

    def test_a_province_reference_must_name_a_captured_province(self):
        bad=built(STEPS[0])
        bad.rows['battle_history']=[(8,6,None,PROVINCE+1,0,0,None,'key',0,None,0.0,0.0,None,None)]
        with self.assertRaisesRegex(RuntimeError,'did not capture'):
            self.store.write(bad,'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)

    def test_names_must_belong_to_the_ruleset(self):
        bad=built(STEPS[0])
        bad.rows['law_history'][0]=(LAW,PLAYER,'law_unknown',0.1,1,None,True,-1)
        with self.assertRaisesRegex(RuntimeError,'not a law_type'):
            self.store.write(bad,'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)

    def test_the_first_write_opens_the_run_and_starts_the_heartbeat_with_progress(self):
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        c=self.store.connection
        run=self.store.run_id
        self.assertTrue(self.store.beater.is_alive())
        time.sleep(.6)
        self.assertEqual(c.execute('select count(*) from run_lost').fetchone(),(0,))
        self.assertEqual(c.execute('select count(*) from run_stalled').fetchone(),(0,))
        beat,age,step,longest=c.execute('select now()-heartbeat_at,now()-progress_at,progress_step,longest_step_ms from run where run_id=%s',(run,)).fetchone()
        self.assertLess(beat.total_seconds(),1)
        self.assertLess(age.total_seconds(),2)
        self.assertTrue(step.startswith('write'))
        self.assertLess(longest,2000)
        self.store.end_run('time')
        self.assertIsNone(self.store.beater)
        self.assertEqual(c.execute('select end_reason,ended_at is not null from run where run_id=%s',(run,)).fetchone(),('time',True))

    def test_a_stalled_run_is_listed_and_the_watchdog_flag_ends_it(self):
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        c=self.store.connection
        run=self.store.run_id
        self.store.beating.set()
        self.store.beater.join()
        c.execute("update run set progress_at=now()-interval '31 seconds',progress_step='validate x' where run_id=%s",(run,))
        self.assertEqual([(r,s) for r,s,_ in c.execute('select run_id,progress_step,stalled_for from run_stalled')],[(run,'validate x')])
        self.store.flag_stalled('validate x',31.2)
        self.assertEqual(c.execute('select end_reason,end_detail from run where run_id=%s',(run,)).fetchone(),
                         ('loop_stalled','validate x made no progress for 31.2 s; the limit is 30 s'))
        self.assertEqual(c.execute('select count(*) from run_stalled').fetchone(),(0,))
        self.store.end_run('time')
        self.assertEqual(c.execute('select end_reason from run where run_id=%s',(run,)).fetchone(),('loop_stalled',))

    def test_a_run_whose_loop_vanished_is_closed_by_the_next_loop_with_its_last_heartbeat(self):
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        c=self.store.connection
        lost=self.store.run_id
        c.execute("update run set heartbeat_at=now()-interval '9 seconds' where run_id=%s",(lost,))
        other=Store(DSN)
        other.begin_run(started_at=datetime(2026,9,23,tzinfo=timezone.utc),kind='attached')
        other.connection.close()
        self.assertEqual(c.execute('select end_reason,ended_at=heartbeat_at from run where run_id=%s',(lost,)).fetchone(),('loop_lost',True))
        self.assertEqual(c.execute('select count(*) from run_lost').fetchone(),(0,))

    def test_verification_is_computed_by_the_database_from_logged_actions(self):
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        c=self.store.connection
        self.store.catalogue(['build','research'])
        for n,(name,status) in enumerate((('build','verified'),('build','verified'),('build','verified'),('research','invalid')),1):
            self.store.log_action({'seq':n,'turn':1,'advisor':'random','action':name,'params':{'state':1},'snapshot':0,'status':status,'detail':'x','ms':1},None)
        rows=dict((a,(r,v,f,w,ok)) for a,r,v,f,w,ok in c.execute('select action,runs,verified,failed,worlds,verified_by_standard from action_verification').fetchall())
        self.assertEqual(rows['build'],(1,3,0,1,False))
        self.assertEqual(rows['research'],(1,0,1,0,False))
        for run in range(2,4):
            with c.transaction():
                c.execute("insert into run (kind,source_session,started_at,heartbeat_at,progress_at,progress_step,world_id,ruleset_id,player_country,game_speed,first_start,"
                          "custom_rng_seed) select 'attached',source_session,started_at,now(),now(),'copy',world_id,ruleset_id,player_country,game_speed,first_start,"
                          "custom_rng_seed from run where run_id=%s",(self.store.run_id,))
                new=c.execute('select max(run_id) from run').fetchone()[0]
                c.execute("insert into snapshot select %s,seq,phase,game_date,taken_at,read_ms,local_date_time,paused,speed,ui_panel_open,ui_interaction_open,ui_map_list_open from snapshot where run_id=%s",(new,self.store.run_id))
                c.execute("insert into country (run_id,country,first_seq) select %s,country,first_seq from country where run_id=%s",(new,self.store.run_id))
                c.execute("insert into loop_action select %s,n,turn,advisor,action,before_seq,after_seq,status,detail,ms,logged_at from loop_action where run_id=%s",(new,self.store.run_id))
        rows=dict((a,(r,v,ok)) for a,r,v,ok in c.execute('select action,runs,verified,verified_by_standard from action_verification').fetchall())
        self.assertEqual(rows['build'],(3,9,True))
        self.assertEqual(rows['research'],(3,0,False))
        for run in c.execute('select run_id from run where run_id<>%s',(self.store.run_id,)).fetchall():
            c.execute('select delete_run(%s)',run)
        self.assertEqual(c.execute('select verified_actions,catalogue_actions,never_attempted from verification_summary').fetchone(),(0,2,0))
        self.assertEqual(c.execute('select world from action_run_outcome').fetchone(),('attached',))

    def test_samples_are_immutable(self):
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        changed=built({**STEPS[1],'samples':[(1,0.9),(2,0.6)]})
        with self.assertRaisesRegex(RuntimeError,'sample'):
            self.store.write(changed,'post_action',datetime(2026,9,23,tzinfo=timezone.utc),1.0)


if __name__=='__main__':
    unittest.main()
