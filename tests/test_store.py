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
    return (ident,definition,'gov_test','faith',None,None,-1,capital,-1,-1,-1,-1,-1,None,None,False,True,False)


def built(step):
    rows=empty()
    rows['country_history']=[country(PLAYER,'AAA',STATE),country(OTHER,'BBB',-1)]
    rows['state_private']=[(STATE,1.5)]
    rows['state_history']=[(STATE,'STATE_TEST','Hometown',PLAYER,-1,-1,-1,False)]
    rows['province_history']=[(PROVINCE,STATE,PLAYER)]
    rows['law_history']=[(LAW,PLAYER,'law_one',step['progress'],1,None,True,-1)]+([(LAW+1,PLAYER,'law_two',0.0,1,None,False,-1)] if step['second'] else [])
    rows['interest_group_history']=[(GROUP,PLAYER,'ig_test','ig_name',-1,-1,0,0,True,0)]
    rows['interest_group_sample']=[(GROUP,n,100*n if n==step['head'] else None,value,1,2) for n,value in step['samples']]
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
        self.assertEqual(c.execute('select n,seq,date,clout from interest_group_sample where run_id=%s order by n',(run,)).fetchall(),
                         [(1,0,100,0.5),(2,1,200,0.6)])
        self.assertEqual(c.execute('select province,color from province where run_id=%s',(run,)).fetchall(),[(PROVINCE,1)])
        self.assertEqual(c.execute("select l.name from law_history h join law_type l using (law_type) where run_id=%s and law=%s limit 1",(run,LAW)).fetchone(),
                         ('law_one',))
        stored=Stored(c,run,2)
        self.assertEqual(stored.rows('law','law,law_type',country=PLAYER),[(LAW,'law_one')])
        self.assertEqual(stored.states(),[STATE])

    def test_references_must_name_captured_objects(self):
        step=dict(STEPS[0])
        bad=built(step)
        bad.rows['law_history'][0]=(LAW,3|GEN,'law_one',0.1,1,None,True,-1)
        with self.assertRaisesRegex(RuntimeError,'did not capture'):
            self.store.write(bad,'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)

    def test_a_stale_handle_to_a_reused_slot_is_not_resolved_to_the_new_object(self):
        bad=built(STEPS[0])
        bad.rows['law_history'][0]=(LAW,PLAYER&0xffffff,'law_one',0.1,1,None,True,-1)
        with self.assertRaisesRegex(RuntimeError,'generation 0'):
            self.store.write(bad,'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)

    def test_names_must_belong_to_the_ruleset(self):
        bad=built(STEPS[0])
        bad.rows['law_history'][0]=(LAW,PLAYER,'law_unknown',0.1,1,None,True,-1)
        with self.assertRaisesRegex(RuntimeError,'not a law_type'):
            self.store.write(bad,'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)

    def test_heartbeat_marks_a_live_run_and_ending_stops_it(self):
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        c=self.store.connection
        run=self.store.run_id
        c.execute("update run set heartbeat_at=now()-interval '5 seconds' where run_id=%s",(run,))
        self.assertEqual([r for r, in c.execute('select run_id from run_lost')],[run])
        self.store.start_heartbeat()
        time.sleep(.6)
        self.assertEqual(c.execute('select count(*) from run_lost').fetchone(),(0,))
        self.assertLess(c.execute('select now()-heartbeat_at from run where run_id=%s',(run,)).fetchone()[0].total_seconds(),1)
        self.store.end_run('time')
        self.assertIsNone(self.store.beater)
        self.assertEqual(c.execute('select end_reason,ended_at is not null from run where run_id=%s',(run,)).fetchone(),('time',True))

    def test_samples_are_immutable(self):
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        changed=built({**STEPS[1],'samples':[(1,0.9),(2,0.6)]})
        with self.assertRaisesRegex(RuntimeError,'sample'):
            self.store.write(changed,'post_action',datetime(2026,9,23,tzinfo=timezone.utc),1.0)


if __name__=='__main__':
    unittest.main()
