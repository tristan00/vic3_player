from typing import Literal

from pydantic import BaseModel

ColumnKind=Literal['number','bool','text','date','time','ref','run','seq','n','action','table','kind','round']
LiveState=Literal['open','ended']


class GameDate(BaseModel):
    hours:int
    text:str


class Ref(BaseModel):
    kind:str
    id:int
    label:str|None
    run:int|None=None


class Cell(BaseModel):
    text:str|None=None
    num:float|None=None
    ref:Ref|None=None


class GridColumn(BaseModel):
    name:str
    label:str
    kind:ColumnKind
    entity:str|None=None
    group:str|None=None


class Grid(BaseModel):
    columns:list[GridColumn]
    rows:list[list[Cell]]
    total:int
    offset:int
    run:int|None
    seq:int|None=None
    last_seq:int|None=None
    game_date:GameDate|None=None
    keys:list[str]|None=None


class Setting(BaseModel):
    name:str
    value:str


class InitializerInfo(BaseModel):
    name:str
    title:str
    settings:list[Setting]


class OpenRun(BaseModel):
    run:int
    country:str
    state:LiveState


class RewardPart(BaseModel):
    component:str
    start_value:float
    end_ratio:float
    recent_change:float
    part:float
    weight:float
    alpha:float
    duration_factor:float
    contribution:float


class RunInfo(BaseModel):
    run:int
    country:str
    player:int
    player_label:str|None
    state:LiveState
    last_seq:int|None
    last_action:int|None
    previous:int|None
    next:int|None


class RunReward(BaseModel):
    name:str
    years:float|None
    window_years:float|None
    baseline_seq:int|None
    score:float|None
    unavailable_reason:str|None=None
    parts:list[RewardPart]


class SeriesChoice(BaseModel):
    table:str
    column:str


class Series(BaseModel):
    table:str
    column:str
    x:Literal['game_hours','sample']
    xs:list[float]
    values:list[float]
    seqs:list[int]
    hours:list[int|None]


class TableCount(BaseModel):
    table:str
    kind:str
    owner:str|None
    keyed:bool
    rows:int


class Reference(BaseModel):
    table:str
    column:str
    rows:int


class TreatyTerm(BaseModel):
    article:Ref
    source:Ref|None
    target:Ref|None


class TreatyInfo(BaseModel):
    seq:int
    first:Ref
    second:Ref
    status:Literal['Proposed','In force','Withdrawn','No longer present']
    entered_into_force_on:GameDate|None
    binding_period_days:int
    binding_until:GameDate|None
    terms:list[TreatyTerm]


class EntityInfo(BaseModel):
    ref:Ref
    first_seq:int
    last_seq:int
    present:bool
    owned:list[TableCount]
    references:list[Reference]
    actions:int
    treaty:TreatyInfo|None=None


class ParamSpec(BaseModel):
    name:str
    kind:str


class ActionInfo(BaseModel):
    action:str
    group:str
    params:list[ParamSpec]
