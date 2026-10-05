from datetime import datetime, timezone
import math
import unittest
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

from advisors.models.histogram.data import PARAMS
from dashboard.server import actions, changes, db, meta, policy, runs, tables
from dashboard.server.app import app
from dashboard.server.grid import Spec, cells
from interface.recording.store import Store
from interface.timing import RECORDER
from tests.test_store import DSN, EFFECTS, ENUMS, LAW, MEMBERS, PLAYER, RUN, STEPS, built, clean

AT=datetime(2026,9,23,tzinfo=timezone.utc)
PROPOSAL={'initializer':'random_smac_weighting','reward':'composite','method':'expected_improvement','observations':12,'best_reward':4.5,'predicted_reward':5.0,'uncertainty':.5,'expected_improvement':.7,
          'beat_probability':.8,'candidates':3,'seconds':.2,'observed':[],'importance':[('build',.6),('enact_law',.4)],
          'candidate_rows':[(0,'local_search',5.0,.5,.7,.8),(1,'random',6.0,.1,.3,.6),(2,'random',3.0,.9,.1,.1)]}


def value(cell):
    if cell.ref:
        return cell.ref.id
    return cell.text if cell.text is not None else cell.num


def rows(grid):
    return [{c.name:value(v) for c,v in zip(grid.columns,row)} for row in grid.rows]


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            connection=psycopg.connect(DSN,autocommit=True)
        except psycopg.OperationalError as error:
            raise unittest.SkipTest(f'test database unavailable: {error}')
        clean(connection)
        connection.close()
        RECORDER.reset()
        from interface.recording.spec import VOCABULARIES
        folders={folder for names in VOCABULARIES.values() if names for folder in names}
        store=Store(DSN)
        store.ruleset(b'rules',{**{f:[] for f in folders},**MEMBERS},[],[],[],[],[],[],ENUMS,[('income',1,'income_taxes')],EFFECTS)
        store.world('ab',[{'color':'x000001','region':'STATE_TEST','terrain':'plains','area_pixels':4,'x':1.0,'y':2.0}],[],{})
        store.session='test'
        store.begin_run(started_at=AT,**RUN)
        store.pending['proposal']=PROPOSAL
        store.pending['pick_model']=(1049,29,4.5,PARAMS,[('treasury',60.0),('action1.type',40.0)])
        for step in STEPS:
            store.write(built(step),'post_action',AT,1.0)
        store.record_pick(0,[['construct_infrastructure','research_production_technology'],['enact_new_law']],[1.5,-2.0],0)
        store.record_pick(1,[['research_production_technology'],['construct_infrastructure']],[0.5,3.0],1)
        store.log_action({'turn':1,'seq':1,'advisor':'random','action':'enact_law','params':{'law':LAW},'snapshot':0,'status':'done','ms':5,
                          'decision':('enact_new_law',{'law':LAW})},1)
        store.log_action({'turn':1,'seq':2,'advisor':'random','action':'research','params':{'technology':'cotton_gin'},'snapshot':0,'status':'invalid',
                          'detail':'not researchable','decision':('research_production_technology',{'technology':'cotton_gin'})},None)
        store.end_run('time')
        cls.run_id=store.run_id
        store.connection.close()
        db.open_pool(DSN)

    @classmethod
    def tearDownClass(cls):
        db.close_pool()

    def test_initializers_are_described_with_the_settings_the_advisors_use(self):
        from advisors.initializers import ADVISORS
        from advisors.models import forest, svr as random_svr_weighting
        found={i['name']:i for i in policy.initializers()}
        self.assertEqual(set(found),set(ADVISORS))
        settings=lambda name:{s['name']:s['value'] for s in found[name]['settings']}
        self.assertEqual(settings('random_smac_weighting')['run history'],'All scored runs')
        self.assertEqual(settings('random_smac_weighting')['features per split'],forest.FEATURES)
        self.assertEqual(settings('random_svr_weighting')['C'],str(random_svr_weighting.C))

    def test_runs_list_counts_actions_and_status(self):
        found=runs.runs_grid([],None,False,0,100)
        row=next(r for r in rows(found) if r['run']==self.run_id)
        self.assertEqual((row['actions'],row['snapshots'],row['state'],row['end_reason']),(2,3,'ended','time'))
        country=next(r for r in found.rows if r[0].ref.id==self.run_id)[[c.name for c in found.columns].index('country')].ref
        self.assertEqual((country.run,country.kind,country.id,country.label),(self.run_id,'country',PLAYER,'AAA'))

    def test_entity_labels_are_resolved_separately_for_each_run(self):
        specs=[Spec('run','run','run_id'),Spec('target','ref','law',entity='law',run='run')]
        with patch('dashboard.server.grid.labels',side_effect=lambda run,kind,ids:{i:f'{run}.{i}' for i in ids}) as lookup:
            result=cells(specs,[[12,7],[13,7],[12,8]],None)
        self.assertEqual([(r[1].ref.run,r[1].ref.label) for r in result],[(12,'12.7'),(13,'13.7'),(12,'12.8')])
        self.assertEqual(lookup.call_count,2)

    def test_snapshot_changes_show_before_and_after(self):
        self.assertIn('law_history',[r['table'] for r in rows(changes.changed_tables(self.run_id,1,[],None,False,0,500))])
        law=next(r for r in rows(changes.table_changes(self.run_id,1,'law_history',[],None,False,0,100)) if r['law']==LAW)
        self.assertEqual((law['progress.before'],law['progress']),(0.1,0.2))
        gone=rows(changes.table_changes(self.run_id,2,'law_history',[],None,False,0,100))
        self.assertEqual([(r['law'],r['present']) for r in gone],[(LAW+1,'no')])

    def test_entities_resolve_at_a_snapshot_and_label_by_vocabulary(self):
        self.assertEqual(tables.entity_grid(self.run_id,'law',1,False,[],None,False,0,100).total,2)
        self.assertEqual(tables.entity_grid(self.run_id,'law',2,False,[],None,False,0,100).total,1)
        self.assertEqual(tables.entity_grid(self.run_id,'law',2,True,[],None,False,0,100).total,2)
        versions=rows(tables.table_grid(self.run_id,'law_history',2,True,[('law',str(LAW))],None,False,0,100))
        self.assertEqual([r['seq'] for r in versions],[0,1])
        info=tables.entity_info(self.run_id,'law',LAW)
        self.assertEqual((info.ref.label,info.actions),('law_one',1))
        self.assertEqual(tables.entity_info(self.run_id,'country',PLAYER).ref.label,'AAA')

    def test_action_params_link_entities_and_stats_split_status(self):
        grid=actions.run_actions(self.run_id,[('n','1')],None,False,0,100)
        law=grid.rows[0][[c.name for c in grid.columns].index('param.law')].ref
        self.assertEqual((law.kind,law.label),('law','law_one'))
        across=actions.action_picks('enact_law',f'run:{self.run_id}',[],None,False,0,100)
        target=across.rows[0][[c.name for c in across.columns].index('param.law')].ref
        self.assertEqual((target.run,target.kind,target.label),(self.run_id,'law','law_one'))
        by_run=actions.action_runs('enact_law',f'run:{self.run_id}',[],None,False,0,100)
        country=by_run.rows[0][1].ref
        self.assertEqual((country.run,country.kind,country.id),(self.run_id,'country',PLAYER))
        stats={r['action']:r for r in rows(actions.action_stats(f'run:{self.run_id}',[],None,False,0,500))}
        self.assertEqual((stats['enact_law']['done'],stats['research']['invalid'],stats['build']['picks']),(1,1,0))
        details=rows(actions.action_details('research',f'run:{self.run_id}',[],None,False,0,100))
        self.assertEqual([(d['status'],d['detail'],d['count']) for d in details],[('invalid','not researchable',1)])

    def test_the_run_records_the_parameters_that_launched_it(self):
        found=db.row('select runs_requested,world_seed,countries,states,tech,pop from run where run_id=%s',(self.run_id,))
        self.assertEqual(found,{'runs_requested':3,'world_seed':9,'countries':2,'states':1,'tech':0.5,'pop':1.5})
        weights=db.rows('select a.name,w.weight from run_weight w join advisor_action a using (advisor_action) where w.run_id=%s order by 1',(self.run_id,))
        self.assertEqual([(w['name'],w['weight']) for w in weights],[('construct_infrastructure',3.0),('laws',2.0)])

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

    def test_meta_tables_resolve_names_and_link_runs(self):
        candidates=rows(meta.meta_grid('smac_candidate',[('run_id',str(self.run_id))],'rank',False,0,100))
        self.assertEqual([(c['run_id'],c['rank'],c['source']) for c in candidates],[(self.run_id,0,'local_search'),(self.run_id,1,'random'),(self.run_id,2,'random')])
        logged=rows(meta.meta_grid('loop_action',[('run_id',str(self.run_id))],'n',False,0,100))
        self.assertEqual([(a['n'],a['action'],a['advisor']) for a in logged],[(1,'enact_law','random'),(2,'research','random')])

    def test_timings_are_stored_for_each_snapshot_and_for_the_whole_run(self):
        write=('span','interface.recording.store.Store.write')
        whole=rows(meta.meta_grid('run_timing',[('run_id',str(self.run_id)),write],None,False,0,100))
        self.assertEqual([(t['run_id'],t['calls'],t['errors']) for t in whole],[(self.run_id,3,0)])
        self.assertLess(whole[0]['self_ms'],whole[0]['total_ms'])
        self.assertLessEqual(whole[0]['min_ms']+whole[0]['max_ms'],whole[0]['total_ms'])
        spans=rows(meta.meta_grid('snapshot_timing',[('run_id',str(self.run_id)),write],'seq',False,0,100))
        self.assertEqual([(s['seq'],s['calls']) for s in spans],[(1,1),(2,1)])
        self.assertLess(sum(s['total_ms'] for s in spans),whole[0]['total_ms'])
        flushes=rows(meta.meta_grid('run_timing',[('run_id',str(self.run_id)),('span','interface.recording.store.Store.record_timing')],None,False,0,100))
        self.assertEqual([t['calls'] for t in flushes],[3])

    def test_run_and_policy_records_split_the_run_table_without_overlap(self):
        run={c.name for c in meta.run_record(self.run_id).columns}
        policy={c.name for c in meta.policy_record(self.run_id).columns}
        self.assertFalse(run&policy)
        self.assertEqual(run|policy,{s.name for s in meta.specs('run')}-{'run_id'}|{'initializer'})
        self.assertNotIn('advisor',[c.name for c in actions.run_actions(self.run_id,[],None,False,0,100).columns])

    def test_picker_offers_count_every_candidate_action(self):
        offers={r['action']:r for r in rows(policy.picker_actions([],None,False,0,100))}
        self.assertEqual((offers['construct_infrastructure']['offered'],offers['construct_infrastructure']['chosen']),(2,2))
        self.assertAlmostEqual(offers['construct_infrastructure']['chosen_share'],2/3)
        self.assertAlmostEqual(offers['construct_infrastructure']['offered_share'],2/5)

    def test_picker_filters_apply_to_offers_models_and_importance(self):
        for table in ('pick_model','pick_importance'):
            matching=meta.meta_grid(table,[('picker','first')],None,False,0,100)
            self.assertGreater(matching.total,0)
            self.assertTrue(all(row['picker']=='first' for row in rows(matching)))
            self.assertEqual(meta.meta_grid(table,[('picker','catboost_piecewise')],None,False,0,100).total,0)
        matching=policy.picker_actions([('picker','first')],None,False,0,100)
        self.assertAlmostEqual(sum(row['offered_share'] for row in rows(matching)),1)
        self.assertEqual(policy.picker_actions([('picker','catboost')],None,False,0,100).total,0)

    def test_configuration_performance_uses_scored_runs_and_keeps_missing_medians_null(self):
        scores={self.run_id:{'years':2,'score':1.,'parts':[{'component':name,'end_ratio':ending,'recent_change':recent}
                                                       for name,ending,recent in [('stock',1.3,.15),('population',1.1,.04),('gdp',1.2,.03)]]}}
        with patch('dashboard.server.policy.reward_scores',return_value=scores):
            found=rows(policy.configs([],'median_reward',True,0,100))[0]
        self.assertEqual((found['runs'],found['scored_runs'],found['median_reward'],found['median_years']),(1,1,1,2))
        self.assertEqual(tuple(round(found[f'median_{c}_gain'],9) for c in ('stock','population','gdp')),(30,10,20))
        self.assertEqual(tuple(round(found[f'median_{c}_recent_change'],9) for c in ('stock','population','gdp')),(15,4,3))
        self.assertNotIn('median_sol_gain',found)
        with patch('dashboard.server.policy.reward_scores',return_value={}):
            found=rows(policy.configs([],None,False,0,100))[0]
        self.assertEqual((found['runs'],found['scored_runs']),(1,0))
        self.assertIsNone(found['median_reward'])
        self.assertIsNone(found['median_gdp_gain'])
        self.assertIsNone(found['median_gdp_recent_change'])

    def test_policy_grid_uses_the_shared_fixed_reward_and_component_contributions(self):
        from advisors.data.endgame import COMPONENTS, HOURS_PER_YEAR, breakdown
        result=breakdown(0,2*HOURS_PER_YEAR,dict.fromkeys(COMPONENTS,100),{name:[(0,100),(HOURS_PER_YEAR,120),(2*HOURS_PER_YEAR,150)] for name in COMPONENTS})
        with patch('dashboard.server.policy.reward_scores',return_value={self.run_id:result}):
            grid=policy.run_policies([],None,False,0,100)
        found=next(r for r in rows(grid) if r['run']==self.run_id)
        self.assertAlmostEqual(found['reward'],result['score'])
        self.assertAlmostEqual(sum(found[f'{c}.contribution'] for c in COMPONENTS),found['reward'])
        self.assertEqual([found[f'{c}.alpha'] for c in COMPONENTS],[.5,1.,-.5])
        self.assertFalse(any(c.name.startswith('objective_') or c.name.startswith('sol.') for c in grid.columns))

    def test_random_initializer_weights_are_exposed_with_their_source(self):
        found=rows(policy.weights([('run',str(self.run_id))],'weight',True,0,100))
        self.assertEqual([(r['initializer'],r['method'],r['domain'],r['action'],r['weight']) for r in found],
                         [('random',None,'construct','construct_infrastructure',3),('random',None,'single','laws',2)])
        response=TestClient(app).get(f'/api/policy/weights?f=run:{self.run_id}')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['total'],2)

    def test_a_column_lists_its_values_with_counts_and_several_values_of_one_column_match_any(self):
        client=TestClient(app)
        listed=client.get(f'/api/policy/weights?f=run:{self.run_id}&values=action').json()
        self.assertEqual([(row[0]['text'],row[1]['num']) for row in listed['rows']],[('construct_infrastructure',1.0),('laws',1.0)])
        self.assertEqual(listed['total'],2)
        narrowed=client.get(f'/api/policy/weights?f=run:{self.run_id}&f=action:construct_infrastructure&values=action').json()
        self.assertEqual(narrowed['total'],2)
        either=client.get(f'/api/policy/weights?f=run:{self.run_id}&f=action:construct_infrastructure&f=action:laws').json()
        self.assertEqual(either['total'],2)
        one=client.get(f'/api/policy/weights?f=run:{self.run_id}&f=action:construct_infrastructure&f=weight:3').json()
        self.assertEqual(one['total'],1)

    def test_the_catalogue_lists_every_advisor_action_with_the_commands_that_carried_it(self):
        from advisors.catalogue import ACTIONS
        found=rows(policy.catalogue([],None,False,0,1000))
        self.assertEqual([row['action'] for row in found],[action.name for action in ACTIONS])
        enacted=next(row for row in found if row['action']=='enact_new_law')
        self.assertEqual((enacted['domain'],enacted['parameters'],enacted['commands'],enacted['executions'],enacted['runs']),('laws','law','enact_law',1,1))
        self.assertEqual(next(row for row in found if row['action']=='raise_tax_level')['executions'],0)
        self.assertEqual(TestClient(app).get('/api/policy/catalogue').status_code,200)

    def test_candidate_rank_and_gap_stay_global_when_filtered_or_paginated(self):
        ranked=rows(policy.candidates(self.run_id,1,[],None,False,0,100))
        self.assertEqual([(r['rank'],r['candidate'],r['chosen'],r['predicted_change'],r['gap'],r['block']) for r in ranked],
                         [(1,1,'yes',3,0,'construct_infrastructure'),(2,0,'no',0.5,2.5,'research_production_technology')])
        self.assertEqual(rows(policy.candidates(self.run_id,1,[],None,False,1,1)),ranked[1:])
        self.assertEqual(rows(policy.candidates(self.run_id,1,[('candidate','0')],None,False,0,100)),ranked[1:])
        self.assertEqual(rows(policy.candidates(self.run_id,0,[],None,False,0,100))[0]['block'],'construct_infrastructure → research_production_technology')
        response=TestClient(app).get(f'/api/policy/runs/{self.run_id}/pauses/1/candidates')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['total'],2)

    def test_routes_answer_and_reject_unknown_names(self):
        RECORDER.reset()
        client=TestClient(app)
        self.assertEqual(client.get(f'/api/runs/{self.run_id}/snapshots/1/tables/law_history').status_code,200)
        self.assertEqual(client.get(f'/api/runs/{self.run_id}/series?table=player_treasury&column=money').status_code,200)
        self.assertEqual(client.get(f'/api/runs/{self.run_id}/entities/nothing').status_code,404)
        self.assertEqual(client.get('/api/actions?scope=bogus').status_code,400)
        self.assertEqual(client.get('/api/runs?sort=bogus').status_code,400)
        self.assertEqual(client.get('/api/meta/bogus').status_code,404)
        self.assertEqual(client.get('/api/nowhere/at/all').status_code,404)
        self.assertEqual(client.post('/api/runs').status_code,404)
        timing=client.get('/api/timing?sort=span')
        self.assertEqual(timing.status_code,200)
        counted={row[0]['text']:row[1]['num'] for row in timing.json()['rows']}
        self.assertEqual({span:calls for span,calls in counted.items() if span.startswith(('GET ','POST '))},
                         {'GET /api/runs/{run_id}/snapshots/{seq}/tables/{table}':1,'GET /api/runs/{run_id}/series':1,'GET /api/runs/{run_id}/entities/{kind}':1,
                          'GET /api/actions':1,'GET /api/runs':1,'GET /api/meta/{table}':1,'GET /api/{path:path}':1,'POST /api/{path:path}':1})
        self.assertGreaterEqual(counted['dashboard.server.db.rows'],1)

    def test_live_stamp_finishes_without_holding_a_stream_open(self):
        response=TestClient(app).get('/api/stamp')
        self.assertEqual(response.status_code,200)
        self.assertIsInstance(response.json(),str)
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertIn('Server-Timing',response.headers)


if __name__=='__main__':
    unittest.main()
