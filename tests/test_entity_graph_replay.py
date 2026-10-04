import copy
import unittest
from unittest.mock import MagicMock, patch

from advisors.models.entity_graph.replay import ReplayReader


class WorldReplayTests(unittest.TestCase):
    def reader(self):
        events={
            'country_history':[
                {'country':1,'seq':0,'present':True,'capital':11},
                {'country':1,'seq':2,'present':False},
                {'country':1,'seq':4,'present':True,'capital':12}],
            'country_population':[{'country':1,'seq':0,'loyalists_increase':7}],
            'country_culture':[{'country':1,'culture':8,'seq':0,'present':True},
                               {'country':1,'culture':8,'seq':3,'present':False}],
            'player_policy':[{'seq':0,'tax_level':1},{'seq':1,'tax_level':2},{'seq':4,'tax_level':3}],
            'country_gdp_sample':[
                {'run_id':1,'country':1,'n':0,'seq':0,'date':None,'gdp':1},
                {'run_id':1,'country':1,'n':1,'seq':0,'date':10,'gdp':2},
                {'run_id':1,'country':1,'n':2,'seq':1,'date':0,'gdp':3},
                {'run_id':1,'country':1,'n':3,'seq':2,'date':3,'gdp':4},
                {'run_id':1,'country':1,'n':4,'seq':3,'date':2,'gdp':5}]}
        connection=MagicMock()
        def execute(sql,args,binary=False):
            self.assertTrue(binary)
            self.assertIn('seq>%s and seq<=%s',sql)
            fields=sql.split('select ',1)[1].split(' from ',1)[0].replace('"','').split(',')
            name=sql.split(' from ',1)[1].split()[0]
            selected=[row for row in events[name] if args[1]<row['seq']<=args[2]]
            cursor=MagicMock()
            cursor.fetchall.return_value=[tuple(row.get(field) for field in fields) for row in selected]
            return cursor
        connection.execute.side_effect=execute
        with patch('advisors.models.entity_graph.replay.WorldReader.__init__',return_value=None),patch('advisors.models.entity_graph.replay.WORLD_TABLES',tuple(events)):
            reader=ReplayReader(connection,1,5,chunk_size=2)
        reader.connection=connection
        reader.run=1
        reader.dates={0:0,1:0,2:2,3:2,4:4,5:10}
        return reader,tuple(events)

    def test_replay_matches_presence_owner_and_sample_time_semantics(self):
        reader,tables=self.reader()
        with patch('advisors.models.entity_graph.replay.WORLD_TABLES',tables):
            first=reader.snapshot(0)
            original=copy.deepcopy(first)
            self.assertEqual(first['country_gdp_sample'][0]['gdp'],1)
            second=reader.snapshot(1)
            self.assertEqual(second['country_gdp_sample'][0]['gdp'],3)
            self.assertEqual(second['player_policy'][0]['tax_level'],2)
            dead=reader.snapshot(2)
            self.assertEqual(dead['country_history'],[])
            self.assertEqual(dead['country_population'],[])
            self.assertEqual(dead['country_gdp_sample'],[])
            self.assertEqual(len(dead['country_culture']),1)
            fourth=reader.snapshot(3)
            self.assertEqual(fourth['country_culture'],[])
            alive=reader.snapshot(4)
            self.assertEqual(alive['country_history'][0]['capital'],12)
            self.assertEqual(alive['country_population'][0]['loyalists_increase'],7)
            self.assertEqual(alive['country_gdp_sample'][0]['gdp'],4)
            self.assertEqual(reader.snapshot(5)['country_gdp_sample'][0]['gdp'],2)
            self.assertEqual(first,original)
            self.assertEqual(reader.connection.execute.call_count,3*len(tables))

    def test_jumping_over_a_loaded_chunk_keeps_its_unconsumed_changes(self):
        first,tables=self.reader()
        jumped,_=self.reader()
        with patch('advisors.models.entity_graph.replay.WORLD_TABLES',tables):
            first.snapshot(0)
            for seq in range(1,6):
                expected=first.snapshot(seq)
            jumped.snapshot(0)
            actual=jumped.snapshot(5)
        self.assertEqual(actual,expected)

    def test_replay_rejects_rewinds_and_future_boundary(self):
        reader,tables=self.reader()
        with patch('advisors.models.entity_graph.replay.WORLD_TABLES',tables):
            reader.snapshot(2)
            with self.assertRaisesRegex(ValueError,'backwards'):
                reader.snapshot(1)
            with self.assertRaisesRegex(ValueError,'boundary'):
                reader.snapshot(6)
            reader.dates[3]=1
            with self.assertRaisesRegex(ValueError,'game time'):
                reader.snapshot(3)


if __name__=='__main__':
    unittest.main()
