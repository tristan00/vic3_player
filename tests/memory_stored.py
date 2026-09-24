from interface.options.stored import Stored
from interface.recording.spec import TABLES
from interface.recording.store import Layout

LAYOUTS={table.name:Layout(table) for table in TABLES}


class Memory(Stored):
    def __init__(self,player,tables,definitions=None):
        self.player=player
        self.hours=1000
        self.date='1836.1.1'
        self.meta={}
        self.tables=set(LAYOUTS)
        self.name_columns={}
        self.names={}
        self.cache={}
        self.given=tables
        self.given_definitions=definitions or {}

    def table(self,table):
        stored=table+'_history' if table+'_history' in self.tables else table
        layout=LAYOUTS[stored]
        names=layout.keys+['seq']+layout.data
        return names,[tuple(row.get(name) for name in names) for row in self.given.get(stored,[])]

    def first_seen(self,table):
        stored=table+'_history' if table+'_history' in self.tables else table
        return {row[table]:position for position,row in enumerate(self.given.get(stored,[]))}

    def definitions(self,folder):
        return self.given_definitions.get(folder,{})

    def order(self,folder):
        return list(self.given_definitions.get(folder,{}))

    @property
    def methods(self):
        return []

    @property
    def dlc(self):
        return []
