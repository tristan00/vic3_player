from datetime import datetime, timezone
import time
import unittest
from unittest import mock

import psycopg

from advisors.models.histogram.data import PARAMS
from interface.options.stored import Stored
from interface.recording.store import Store, digest, install
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
         'common/buildings':['building_farm'],'common/interest_groups':['ig_test'],'common/government_types':['gov_test'],'common/religions':['faith'],
         'common/production_methods':['pm_farm'],'common/goods':['grain','tools'],'common/pop_types':['farmers','soldiers']}
EFFECTS={'goods':[('pm_farm','grain','output','workforce_scaled',20.0),('pm_farm','tools','input','workforce_scaled',5.0)],
         'employment':[('pm_farm','farmers','level_scaled',1000.0)],'modifiers':[('pm_farm','state','unscaled','state_pollution_generation_add',2.0)],
         'requirements':[('pm_farm','unlocking_technologies','tech_x')],'ratios':[('pm_farm','soldiers',97.0)]}
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


RUN={'kind':'mini','advisors':['random'],'tag':'AAA','world':'w','cli_seed':1,'run_seed':2,'years':1.0,'minutes':1.0,'profile':'actions','pool':0,'runs_requested':3,
     'generated':{'seed':9,'countries':2,'states':1,'tech':0.5,'pop':1.5,'modernity':0.25,'copies':0.2,'diversity':0.5,'military':0.75},'weights':{'construct_infrastructure':3,'laws':2},
     'picker':'first','candidates':1,'objective':({'gdp':0.0,'population':1.0,'sol':0.0,'stock':0.0},0.0)}
STEPS=[{'progress':0.1,'second':True,'head':1,'samples':[(1,0.5)]},
       {'progress':0.2,'second':True,'head':2,'samples':[(1,0.5),(2,0.6)]},
       {'progress':0.2,'second':False,'head':2,'samples':[(2,0.6)]}]


def clean(connection):
    installed=connection.execute("select to_regclass('schema_digest') is not null").fetchone()[0]
    if installed and connection.execute('select digest from schema_digest').fetchone()==(digest(),):
        for run, in connection.execute('select run_id from run order by run_id desc').fetchall():
            connection.execute('select delete_run(%s)',(run,))
    else:
        install(connection)


class Still:
    exitcode=None

    def __init__(self,target,args,daemon,name):
        self.stop=args[5]
        self.killed=False

    def start(self):
        pass

    def is_alive(self):
        return not self.killed and not self.stop.is_set()

    def kill(self):
        self.killed=True

    def join(self,timeout=None):
        pass


BEATING={'test_the_first_write_opens_the_run_and_starts_the_heartbeat_with_progress',
         'test_a_run_whose_loop_vanished_is_closed_by_the_next_loop_with_its_last_heartbeat'}


class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            connection=psycopg.connect(DSN,autocommit=True)
        except psycopg.OperationalError as error:
            raise unittest.SkipTest(f'test database unavailable: {error}')
        clean(connection)
        connection.close()

    def setUp(self):
        if self._testMethodName not in BEATING:
            still=mock.patch('multiprocessing.Process',Still)
            still.start()
            self.addCleanup(still.stop)
        self.store=Store(DSN)
        self.store.ruleset(b'rules',{folder:list(names) for folder,names in {**{f:[] for f in self.folders()},**MEMBERS}.items()},[],[],[],[],[],[],ENUMS,
                             [('income',1,'income_taxes')],EFFECTS)
        self.store.world('ab',[{'color':'x000001','region':'STATE_TEST','terrain':'plains','area_pixels':4,'x':1.0,'y':2.0}],[],{})
        self.store.session='test'
        self.store.begin_run(started_at=datetime(2026,9,23,tzinfo=timezone.utc),**RUN)

    def tearDown(self):
        if self.store.beater is not None:
            self.store.beater.kill()
            self.store.beater.join()
        if self.store.run_id is not None:
            self.store.connection.execute('select delete_run(%s)',(self.store.run_id,))
        self.store.connection.close()

    def folders(self):
        from interface.recording.spec import VOCABULARIES
        return {folder for folders in VOCABULARIES.values() if folders for folder in folders}

    def write_all(self):
        for step in STEPS:
            self.store.write(built(step),'post_action',datetime(2026,9,23,tzinfo=timezone.utc),1.0)

    def test_world_controls_are_recorded_with_source_government_default(self):
        self.store.pending['generated']={**RUN['generated'],'modernity':None,'ideology_uniformity':.4,'primary_culture_share':.7,'tech_variation':1.2,'country_economy':.8,'local_economy':1.1,'source_regions':2}
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        row=self.store.connection.execute('select ideology_uniformity,primary_culture_share,copies,tech_variation,country_economy,local_economy,source_regions from run where run_id=%s',(self.store.run_id,)).fetchone()
        self.assertEqual(row,(.4,.7,.2,1.2,.8,1.1,2))

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

    def test_validation_refuses_a_written_value_whose_target_is_missing(self):
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        names=self.store.layouts['law_history'].names
        rows=self.store.connection.execute(f'select {",".join(names)} from law_history where run_id=%s',(self.store.run_id,)).fetchall()
        broken=[tuple(-5 if name=='law_type' else value for name,value in zip(names,rows[0]))]
        with self.store.connection.cursor() as cursor:
            self.store.validate(cursor,0,{'law_history':(names,rows)})
            with self.assertRaisesRegex(RuntimeError,r'law_history\(law_type\) -> law_type'):
                self.store.validate(cursor,0,{'law_history':(names,broken)})

    def test_validation_asks_nothing_about_tables_that_wrote_no_rows(self):
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        names=self.store.layouts['law_history'].names
        with self.store.connection.cursor() as cursor,mock.patch.object(self.store,'connection',wraps=self.store.connection) as asked:
            self.store.validate(cursor,0,{'law_history':(names,[])})
        asked.execute.assert_not_called()

    def test_names_must_belong_to_the_ruleset(self):
        bad=built(STEPS[0])
        bad.rows['law_history'][0]=(LAW,PLAYER,'law_unknown',0.1,1,None,True,-1)
        with self.assertRaisesRegex(RuntimeError,'not a law_type'):
            self.store.write(bad,'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)

    def test_the_first_write_opens_the_run_and_starts_the_heartbeat_with_progress(self):
        since=self.store.connection.execute('select clock_timestamp()').fetchone()[0]
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        c=self.store.connection
        analyzed={name for name, in c.execute('select relname from pg_class where pg_stat_get_last_analyze_time(oid)>=%s',(since,))}
        self.assertLessEqual({'country','law','law_history','state_history','player_treasury'},analyzed)
        run=self.store.run_id
        self.assertTrue(self.store.beater.is_alive())
        beats=set()
        deadline=time.monotonic()+3
        while len(beats)<4:
            self.assertLess(time.monotonic(),deadline,f'{len(beats)} heartbeats arrived')
            beats.add(c.execute('select heartbeat_at from run where run_id=%s',(run,)).fetchone()[0])
            time.sleep(.02)
        self.assertEqual(c.execute('select count(*) from run_lost').fetchone(),(0,))
        self.assertEqual(c.execute('select count(*) from run_stalled').fetchone(),(0,))
        beat,age,step,longest=c.execute('select now()-heartbeat_at,now()-progress_at,progress_step,longest_step_ms from run where run_id=%s',(run,)).fetchone()
        self.assertLess(beat.total_seconds(),1)
        self.assertLess(age.total_seconds(),2)
        self.assertIn('write',step)
        self.assertLess(longest,2000)
        self.store.end_run('time')
        self.assertIsNone(self.store.beater)
        beats,errors=c.execute("select calls,errors from run_timing where run_id=%s and span='interface.recording.store.heartbeat.beat'",(run,)).fetchone()
        self.assertGreaterEqual(beats,3)
        self.assertEqual(errors,0)
        self.assertEqual(c.execute('select end_reason,ended_at is not null from run where run_id=%s',(run,)).fetchone(),('time',True))

    def test_a_policy_proposal_is_written_with_the_run(self):
        self.store.pending['proposal']={'initializer':'random_smac_weighting','reward':'composite','method':'expected_improvement','observations':12,'best_reward':4.5,'predicted_reward':5.0,'uncertainty':.5,
                                        'expected_improvement':.7,'beat_probability':.8,'candidates':2,'seconds':.2,'observed':[],
                                        'candidate_rows':[(0,'local_search',5.0,.5,.7,.8),(1,'random',3.0,.2,.1,.1)],'importance':[('build',.6),('enact_law',.4)]}
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        c=self.store.connection
        run=self.store.run_id
        self.assertEqual(c.execute('select method,observations,predicted_reward,candidates from smac_proposal where run_id=%s',(run,)).fetchone(),('expected_improvement',12,5.0,2))
        self.assertEqual(c.execute('select rank,source from smac_candidate where run_id=%s order by rank',(run,)).fetchall(),[(0,'local_search'),(1,'random')])
        self.assertEqual(c.execute('select dimension,importance from smac_importance where run_id=%s order by dimension',(run,)).fetchall(),[('build',.6),('enact_law',.4)])
        self.store.end_run('time')

    def test_an_svr_proposal_is_written_with_its_observations_and_coefficients(self):
        self.store.pending['proposal']={'initializer':'random_svr_weighting','method':'bootstrap_svr','observations':12,'c':.1,'epsilon':.5,'predicted_reward':1.2,
                                        'bounded':1,'seconds':.3,'observed':[],'coefficients':[('build',.4,-.1,2.0),('enact_law',-.2,-.05,-2.0)]}
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        c=self.store.connection
        run=self.store.run_id
        self.assertEqual(c.execute('select method,observations,predicted_reward,bounded from svr_proposal where run_id=%s',(run,)).fetchone(),('bootstrap_svr',12,1.2,1))
        self.assertEqual(c.execute('select dimension,linear,chosen from svr_coefficient where run_id=%s order by dimension',(run,)).fetchall(),[('build',.4,2.0),('enact_law',-.2,-2.0)])
        self.store.end_run('time')

    def test_an_executed_decision_is_stored_with_its_advisor_action_and_parameters_beside_the_command(self):
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        self.store.log_action({'turn':1,'seq':1,'advisor':'random','action':'set_import_tariff','params':{'goods':'grain','level':'High'},'snapshot':0,'status':'done','ms':5,
                               'decision':('raise_import_tariff',{'goods':'grain'})},None)
        self.store.log_action({'turn':1,'seq':2,'advisor':'loop','action':'unpause','params':{},'snapshot':0,'status':'done','ms':5,'decision':None},None)
        c=self.store.connection
        run=self.store.run_id
        self.assertEqual(c.execute('select l.n,a.name,d.name from loop_action l join action a using (action) left join advisor_action d using (advisor_action) '
                                   'where l.run_id=%s order by 1',(run,)).fetchall(),[(1,'set_import_tariff','raise_import_tariff'),(2,'unpause',None)])
        self.assertEqual(c.execute('select n,name,text_value from loop_decision_param where run_id=%s',(run,)).fetchall(),[(1,'goods','grain')])
        self.assertEqual(c.execute('select n,name,text_value from loop_action_param where run_id=%s order by 2',(run,)).fetchall(),[(1,'goods','grain'),(1,'level','High')])
        self.store.end_run('time')

    def test_picks_record_every_candidate_with_its_actions_and_the_model_behind_them(self):
        self.store.pending['pick_model']=(1049,29,4.5,PARAMS,[('treasury',60.0),('action1.type',40.0)])
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        self.store.record_pick(0,[['construct_infrastructure','research_production_technology'],['enact_new_law']],[1.5,-2.0],0)
        c=self.store.connection
        run=self.store.run_id
        self.assertEqual(c.execute('select pauses,runs from pick_model where run_id=%s',(run,)).fetchone(),(1049,29))
        self.assertEqual(c.execute('select feature,importance from pick_importance where run_id=%s order by 1',(run,)).fetchall(),[('action1.type',40.0),('treasury',60.0)])
        self.assertEqual(c.execute('select candidate,actions,predicted_change,chosen from pick_candidate where run_id=%s order by candidate',(run,)).fetchall(),
                         [(0,2,1.5,True),(1,1,-2.0,False)])
        self.assertEqual(c.execute('select p.candidate,p.position,a.name from pick_candidate_action p join advisor_action a using (advisor_action) where run_id=%s order by 1,2',(run,)).fetchall(),
                         [(0,0,'construct_infrastructure'),(0,1,'research_production_technology'),(1,0,'enact_new_law')])
        self.store.end_run('time')

    def test_row_model_records_its_own_parameters_and_training_row_count(self):
        from advisors.models.row.model import Model
        params={key:value for key,value in Model().params.items() if key!='allow_writing_files'}
        params.update(model_kind='row',training_rows=1234,grow_policy='Lossguide',min_data_in_leaf=20,max_leaves=32,
                      bootstrap_type='Bayesian',bagging_temperature=1.5,border_count=64,leaf_estimation_iterations=3)
        self.store.pending['picker']='catboost_piecewise'
        self.store.pending['pick_model']=(100,12,.5,params,[('action',100.)])
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.)
        row=self.store.connection.execute('select r.picker,m.model_kind,m.training_rows,m.max_ctr_complexity,m.bootstrap_type,'
                                          'm.grow_policy,m.min_data_in_leaf,m.max_leaves,m.bagging_temperature,m.border_count,m.leaf_estimation_iterations '
                                          'from run r join pick_model m using(run_id) where run_id=%s',(self.store.run_id,)).fetchone()
        self.assertEqual(row,('catboost_piecewise','row',1234,params.get('max_ctr_complexity'),'Bayesian','Lossguide',20,32,1.5,64,3))
        self.store.end_run('time')

    def test_a_stalled_run_is_listed_and_the_watchdog_flag_ends_it(self):
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        c=self.store.connection
        run=self.store.run_id
        self.store.beating.set()
        self.store.beater.join()
        c.execute("update run set progress_at=now()-interval '6 seconds',progress_step='validate x' where run_id=%s",(run,))
        self.assertEqual([(r,s) for r,s,_ in c.execute('select run_id,progress_step,stalled_for from run_stalled')],[(run,'validate x')])
        self.store.flag_stalled('validate x',31.2)
        self.assertEqual(c.execute('select end_reason,end_detail from run where run_id=%s',(run,)).fetchone(),
                         ('loop_stalled','validate x made no progress for 31.2 s; the limit is 5 s'))
        self.assertEqual(c.execute('select count(*) from run_stalled').fetchone(),(0,))
        self.store.end_run('time')
        self.assertEqual(c.execute('select end_reason from run where run_id=%s',(run,)).fetchone(),('loop_stalled',))

    def test_a_run_whose_loop_vanished_is_closed_by_the_next_loop_with_its_last_heartbeat(self):
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        c=self.store.connection
        lost=self.store.run_id
        self.store.beater.kill()
        self.store.beater.join()
        deadline=time.monotonic()+3
        while c.execute('select count(*) from pg_stat_activity where datname=current_database() and pid<>pg_backend_pid()').fetchone()[0]:
            self.assertLess(time.monotonic(),deadline,'the killed heartbeat kept its database session')
            time.sleep(.01)
        c.execute("update run set heartbeat_at=now()-interval '9 seconds' where run_id=%s",(lost,))
        other=Store(DSN)
        other.begin_run(started_at=datetime(2026,9,23,tzinfo=timezone.utc),**RUN)
        other.connection.close()
        self.assertEqual(c.execute('select end_reason,ended_at=heartbeat_at from run where run_id=%s',(lost,)).fetchone(),('loop_lost',True))
        self.assertEqual(c.execute('select count(*) from run_lost').fetchone(),(0,))

    def test_run_ids_count_from_one_without_a_gap_even_after_a_deletion(self):
        c=self.store.connection
        runs=[]
        for _ in range(3):
            self.store.begin_run(started_at=datetime(2026,9,23,tzinfo=timezone.utc),**RUN)
            self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
            runs.append(self.store.run_id)
        self.assertEqual(runs,[1,2,3])
        laws=c.execute('select count(*) from law_history where run_id=3').fetchone()
        c.execute('select delete_run(2)')
        self.assertEqual(c.execute('select array_agg(run_id order by run_id) from run').fetchone(),([1,2],))
        self.assertEqual(c.execute('select count(*) from law_history where run_id=2').fetchone(),laws)
        with self.assertRaisesRegex(psycopg.errors.RaiseException,'without a gap'):
            with c.transaction():
                c.execute('set local session_replication_role=replica')
                c.execute('delete from run where run_id=1')
        clean(c)
        self.store.run_id=None

    def test_samples_are_immutable(self):
        self.store.write(built(STEPS[0]),'start',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        changed=built({**STEPS[1],'samples':[(1,0.9),(2,0.6)]})
        with self.assertRaisesRegex(RuntimeError,'sample'):
            self.store.write(changed,'post_action',datetime(2026,9,23,tzinfo=timezone.utc),1.0)


if __name__=='__main__':
    unittest.main()
