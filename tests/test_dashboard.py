from datetime import datetime, timezone
import unittest

import psycopg
from fastapi.testclient import TestClient

from dashboard.server import actions, changes, db, entities, runs
from dashboard.server.app import app
from interface.recording.store import Store, install
from tests.test_store import DSN, EFFECTS, ENUMS, LAW, MEMBERS, PLAYER, RUN, STEPS, built

AT=datetime(2026,9,23,tzinfo=timezone.utc)


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            connection=psycopg.connect(DSN,autocommit=True)
        except psycopg.OperationalError as error:
            raise unittest.SkipTest(f'test database unavailable: {error}')
        install(connection)
        connection.close()
        from interface.recording.spec import VOCABULARIES
        folders={folder for names in VOCABULARIES.values() if names for folder in names}
        store=Store(DSN)
        store.ruleset(b'rules',{**{f:[] for f in folders},**MEMBERS},[],[],[],[],[],ENUMS,[('income',1,'income_taxes')],EFFECTS)
        store.world('ab',[{'color':'x000001','region':'STATE_TEST','terrain':'plains','area_pixels':4,'x':1.0,'y':2.0}],[],{})
        store.session='test'
        store.begin_run(started_at=AT,**RUN)
        for step in STEPS:
            store.write(built(step),'post_action',AT,1.0)
        store.log_action({'turn':1,'seq':1,'advisor':'random','action':'enact_law','params':{'law':LAW},'snapshot':0,'status':'done','ms':5},1)
        store.log_action({'turn':1,'seq':2,'advisor':'random','action':'research','params':{'technology':'cotton_gin'},'snapshot':0,'status':'invalid',
                          'detail':'not researchable'},None)
        store.end_run('time')
        cls.run_id=store.run_id
        store.connection.close()
        db.open_pool(DSN)

    @classmethod
    def tearDownClass(cls):
        db.close_pool()

    def test_runs_list_counts_actions_and_status(self):
        page=runs.runs_page(0,10,'run_id',True)
        row=next(r for r in page.rows if r.run_id==self.run_id)
        self.assertEqual((row.actions,row.done.n,row.snapshots,row.state,row.end_reason),(2,1,3,'ended','time'))

    def test_snapshot_changes_show_before_and_after(self):
        summary=changes.snapshot_changes(self.run_id,1)
        self.assertIn('law_history',[t.table for t in summary.tables])
        self.assertEqual([a.n for a in summary.actions],[1])
        law=changes.table_changes(self.run_id,1,'law_history',0,100)
        changed=next(r for r in law.rows if r.keys[0].ref.id==LAW)
        progress=[c.name for c in law.columns].index('progress')
        self.assertEqual((changed.changed,changed.before[progress].num,changed.cells[progress].num),(['progress'],0.1,0.2))
        gone=changes.table_changes(self.run_id,2,'law_history',0,100)
        self.assertEqual([(r.keys[0].ref.id,r.present) for r in gone.rows],[(LAW+1,False)])

    def test_entities_resolve_at_a_snapshot_and_label_by_vocabulary(self):
        self.assertEqual(entities.entity_list(self.run_id,'law',1,0,100,False).total.value,2)
        self.assertEqual(entities.entity_list(self.run_id,'law',2,0,100,False).total.value,1)
        self.assertEqual(entities.entity_list(self.run_id,'law',2,0,100,True).total.value,2)
        detail=entities.entity_detail(self.run_id,'law',LAW)
        self.assertEqual(detail.ref.label,'law_one')
        self.assertEqual([v.seq for v in detail.history.groups[0].versions],[0,1])
        self.assertEqual([a.n for a in detail.actions],[1])
        country=entities.entity_detail(self.run_id,'country',PLAYER)
        self.assertEqual(country.ref.label,'AAA')

    def test_action_params_link_entities_and_stats_split_status(self):
        detail=actions.action_detail(self.run_id,1)
        self.assertEqual((detail.action.params[0].ref.kind,detail.action.params[0].ref.label),('law','law_one'))
        self.assertEqual([a.n for a in detail.batch],[2])
        stats=actions.action_stats(f'run:{self.run_id}')
        self.assertEqual({(r.action,s.status):s.count for r in stats.rows for s in r.statuses if s.count},{('enact_law','done'):1,('research','invalid'):1})
        kind=actions.action_type('research',f'run:{self.run_id}')
        self.assertEqual([(d.status,d.detail,d.count) for d in kind.details],[('invalid','not researchable',1)])

    def test_the_run_records_the_parameters_that_launched_it(self):
        found=db.row('select runs_requested,world_seed,countries,states,tech,pop from run where run_id=%s',(self.run_id,))
        self.assertEqual(found,{'runs_requested':3,'world_seed':9,'countries':2,'states':1,'tech':0.5,'pop':1.5})
        weights=db.rows('select a.name,w.weight from run_weight w join action a using (action) where w.run_id=%s order by 1',(self.run_id,))
        self.assertEqual([(w['name'],w['weight']) for w in weights],[('build',3.0),('enact_law',2.0)])
        params=db.rows('select a.name,w.param,w.value,w.weight from run_param_weight w join action a using (action) where w.run_id=%s',(self.run_id,))
        self.assertEqual(params,[{'name':'build','param':'building_type','value':'building_x','weight':3.0}])

    def test_production_method_effects_are_stored_typed(self):
        ruleset=db.value('select ruleset_id from run where run_id=%s',(self.run_id,))
        goods=db.rows('select p.name as method,g.name as goods,x.direction,x.scaling,x.amount from production_method_goods x join production_method p using (production_method) '
                      'join goods g using (goods) where x.ruleset_id=%s order by 2',(ruleset,))
        self.assertEqual([tuple(r.values()) for r in goods],[('pm_farm','grain','output','workforce_scaled',20.0),('pm_farm','tools','input','workforce_scaled',5.0)])
        jobs=db.rows('select t.name,x.scaling,x.amount from production_method_employment x join pop_type t using (pop_type) where x.ruleset_id=%s',(ruleset,))
        self.assertEqual([tuple(r.values()) for r in jobs],[('farmers','level_scaled',1000.0)])
        self.assertEqual(db.value('select count(*) from production_method_modifier where ruleset_id=%s',(ruleset,)),1)
        self.assertEqual(db.value('select key from production_method_requirement where ruleset_id=%s',(ruleset,)),'tech_x')
        self.assertEqual(db.value('select ratio from production_method_profession_ratio where ruleset_id=%s',(ruleset,)),97.0)

    def test_routes_answer_and_reject_unknown_names(self):
        client=TestClient(app)
        self.assertEqual(client.get(f'/api/runs/{self.run_id}/snapshots/1/tables/law_history').status_code,200)
        self.assertEqual(client.get(f'/api/runs/{self.run_id}/series?table=player_treasury&column=money').status_code,200)
        self.assertEqual(client.get(f'/api/runs/{self.run_id}/entities/nothing').status_code,404)
        self.assertEqual(client.get('/api/actions?scope=bogus').status_code,400)


class MedianYearOverYearTests(unittest.TestCase):
    def test_growth_compares_each_value_with_the_one_a_game_year_earlier(self):
        year=runs.HOURS_PER_YEAR
        self.assertAlmostEqual(runs.median_yoy([(0,100),(year,110),(2*year,121)]),.1)
        self.assertAlmostEqual(runs.median_yoy([(0,100),(year,90),(year+240,80)]),-.15)
        self.assertIsNone(runs.median_yoy([(0,100),(year-1,105)]))


if __name__=='__main__':
    unittest.main()
