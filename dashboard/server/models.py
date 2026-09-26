from typing import Literal

from pydantic import BaseModel, Field

Status=Literal['done','invalid','raced','no_object','ui_leftover']
LiveState=Literal['running','stalled','lost','ended']
ColumnKind=Literal['number','bool','text','date','ref','vocab','enum']


class Count(BaseModel):
    value:int
    noun:str=Field(min_length=1)
    population:str=Field(min_length=1)


class Rate(BaseModel):
    n:int
    of:int
    noun:str=Field(min_length=1)
    population:str=Field(min_length=1)


class Scope(BaseModel):
    text:str=Field(min_length=1)
    detail:str|None=None


class Ref(BaseModel):
    kind:str
    id:int
    label:str|None


class Cell(BaseModel):
    text:str|None=None
    num:float|None=None
    ref:Ref|None=None


class Column(BaseModel):
    name:str
    kind:ColumnKind
    entity:str|None=None


class StatusCount(BaseModel):
    status:Status
    count:int


class GameDate(BaseModel):
    hours:int
    text:str


class RunRow(BaseModel):
    run_id:int
    round:int
    kind:str
    tag:str
    world:str
    advisors:list[str]
    started_at:str
    ended_at:str|None
    wall_s:float
    minutes:float
    years:float
    end_reason:str|None
    end_detail:str|None
    state:LiveState
    snapshots:int
    game_from:GameDate|None
    game_to:GameDate|None
    actions:int
    done:Rate
    gdp_start:float|None
    gdp_end:float|None
    gdp_peak:float|None
    gdp_yoy:float|None
    population_yoy:float|None


class Facet(BaseModel):
    value:str
    count:int


class RunsPage(BaseModel):
    scope:Scope
    total:Count
    rows:list[RunRow]
    kinds:list[Facet]
    end_reasons:list[Facet]
    tags:list[Facet]


class RoundRow(BaseModel):
    round:int
    runs:int
    live:int
    started_at:str
    last_at:str
    kinds:list[Facet]
    tags:list[str]
    end_reasons:list[Facet]
    actions:int|None


class RoundsPage(BaseModel):
    scope:Scope
    total:Count
    rows:list[RoundRow]


class Param(BaseModel):
    name:str
    kind:str
    text:str
    ref:Ref|None=None


class ActionRow(BaseModel):
    run_id:int
    n:int
    turn:int
    action:str
    group:str
    advisor:str
    status:Status
    detail:str|None
    ms:int|None
    before_seq:int
    after_seq:int|None
    game_date:GameDate
    logged_at:str
    params:list[Param]


class ActionLog(BaseModel):
    scope:Scope
    total:Count
    rows:list[ActionRow]
    actions:list[Facet]
    groups:list[Facet]
    statuses:list[StatusCount]


class SnapshotRow(BaseModel):
    seq:int
    phase:str
    game_date:GameDate
    taken_at:str
    read_ms:float
    paused:bool|None
    speed:int|None
    ui_panel_open:bool
    ui_interaction_open:bool
    ui_map_list_open:bool
    actions:int


class SnapshotsPage(BaseModel):
    scope:Scope
    total:Count
    rows:list[SnapshotRow]


class SeriesChoice(BaseModel):
    table:str
    column:str
    kind:Literal['singleton','sample','subject','history','child']
    label:str


class EntityKindRow(BaseModel):
    kind:str
    live:int
    ever:int
    tables:int


class Weight(BaseModel):
    action:str
    weight:float


class ParamWeight(BaseModel):
    action:str
    param:str
    value:str
    weight:float


class RunDetail(BaseModel):
    run:RunRow
    runs_requested:int
    world_seed:int|None
    countries:int|None
    states:int|None
    tech:float|None
    pop:float|None
    weights:list[Weight]
    param_weights:list[ParamWeight]
    player:Ref
    world_id:int
    ruleset_id:int
    run_seed:int
    cli_seed:int
    profile:str
    pool:int
    game_speed:int
    custom_rng_seed:str
    rules:list[str]
    progress_step:str
    heartbeat_age_s:float
    progress_age_s:float
    longest_step:str|None
    longest_step_ms:int|None
    game_exited_at:str|None
    statuses:list[StatusCount]
    groups:list['GroupStatus']
    read_ms:list[float]
    read_seq:list[int]
    series:list[SeriesChoice]
    entities:list[EntityKindRow]


class GroupStatus(BaseModel):
    group:str
    statuses:list[StatusCount]
    total:int


class Series(BaseModel):
    table:str
    column:str
    label:str
    title:str
    x:Literal['game_hours','sample']
    xs:list[float]
    values:list[float]
    seqs:list[int]
    hours:list[int|None]
    scope:Scope


class Version(BaseModel):
    seq:int
    game_date:GameDate
    present:bool
    cells:list[Cell]
    before:list[Cell]|None=None


class TableChanges(BaseModel):
    table:str
    kind:str
    owner:str|None
    keys:list[Column]
    columns:list[Column]
    rows:list['ChangeRow']
    total:int


class ChangeRow(BaseModel):
    keys:list[Cell]
    present:bool
    cells:list[Cell]
    before:list[Cell]|None
    changed:list[str]


class TableCount(BaseModel):
    table:str
    kind:str
    owner:str|None
    rows:int


class SnapshotChanges(BaseModel):
    scope:Scope
    snapshot:SnapshotRow
    previous:SnapshotRow|None
    tables:list[TableCount]
    actions:list[ActionRow]


class ActionDetail(BaseModel):
    action:ActionRow
    batch:list[ActionRow]
    before:SnapshotRow
    after:SnapshotRow|None


class EntityRow(BaseModel):
    ref:Ref
    first_seq:int
    present:bool
    cells:list[Cell]


class EntityList(BaseModel):
    scope:Scope
    kind:str
    seq:int
    game_date:GameDate
    total:Count
    columns:list[Column]
    rows:list[EntityRow]


class KeyedVersions(BaseModel):
    keys:list[Cell]
    versions:list[Version]


class EntityTable(BaseModel):
    table:str
    kind:str
    keys:list[Column]
    columns:list[Column]
    groups:list[KeyedVersions]
    rows:int


class EntityDetail(BaseModel):
    ref:Ref
    first_seq:int
    last_seq:int
    present:bool
    history:EntityTable|None
    tables:list[TableCount]
    series:list[Series]
    actions:list[ActionRow]
    scope:Scope


class ActionStat(BaseModel):
    action:str
    group:str
    total:int
    runs:int
    statuses:list[StatusCount]
    ms_median:float|None
    ms_p90:float|None


class ActionStats(BaseModel):
    scope:Scope
    total:Count
    runs:Count
    statuses:list[StatusCount]
    groups:list[GroupStatus]
    rows:list[ActionStat]
    never:list[str]


class DetailCount(BaseModel):
    status:Status
    detail:str|None
    count:int


class RunStatus(BaseModel):
    run_id:int
    tag:str
    statuses:list[StatusCount]
    total:int


class ParamSpec(BaseModel):
    name:str
    kind:str


class ActionType(BaseModel):
    scope:Scope
    action:str
    group:str
    params:list[ParamSpec]
    weight:float
    total:Count
    statuses:list[StatusCount]
    details:list[DetailCount]
    runs:list[RunStatus]
    recent:list[ActionRow]


class LiveRun(BaseModel):
    run:RunRow
    player:Ref
    progress_step:str
    heartbeat_age_s:float
    progress_age_s:float
    turn:int
    game_start:GameDate|None
    game_now:GameDate|None
    statuses:list[StatusCount]
    recent:list[ActionRow]
    read_ms:list[float]
    read_seq:list[int]


class LivePage(BaseModel):
    now:str
    live:list[LiveRun]
    blocks:dict[int,list['BlockRow']]
    last:RunRow|None
    round:RoundRow|None


class SchemaColumn(BaseModel):
    name:str
    type:str
    kind:ColumnKind
    target:str|None
    optional:bool


class SchemaTable(BaseModel):
    name:str
    kind:str
    owner:str|None
    scope:str
    keys:list[SchemaColumn]
    columns:list[SchemaColumn]


class CaptureGap(BaseModel):
    kind:str
    subject:str
    detail:str


class SchemaPage(BaseModel):
    entities:list[str]
    tables:list[SchemaTable]
    ruleset_id:int|None
    gaps:list[CaptureGap]


RunDetail.model_rebuild()
TableChanges.model_rebuild()


class CountryTrack(BaseModel):
    ref:Ref
    player:bool
    states:list[int|None]
    provinces:list[int|None]
    population:list[float|None]
    gdp:list[float|None]
    exports:list[float|None]
    imports:list[float|None]


class CountryProgress(BaseModel):
    scope:Scope
    seqs:list[int]
    hours:list[int]
    countries:list[CountryTrack]


class MarketRow(BaseModel):
    market:int
    owner:Ref
    goods:int
    player:bool


class MarketGoods(BaseModel):
    goods:str
    price:float
    base:float|None
    sell:float
    buy:float


class TradePage(BaseModel):
    scope:Scope
    seq:int
    game_date:GameDate
    markets:list[MarketRow]
    market:int|None
    goods:list[MarketGoods]


class TradeSeries(BaseModel):
    goods:str
    market:int
    seqs:list[int]
    hours:list[int]
    price:list[float|None]
    sell:list[float|None]
    buy:list[float|None]
    world_n:list[int]
    world_price:list[float]
    scope:Scope


class BlockRow(BaseModel):
    before_seq:int
    after_seq:int|None
    turn:int
    game_date:GameDate
    kind:Literal['decision','events','time']
    actions:int
    ms:int
    names:list[str]
    statuses:list[StatusCount]


class BlockLog(BaseModel):
    scope:Scope
    total:Count
    rows:list[BlockRow]
    kinds:list[Facet]


class BlockDetail(BaseModel):
    block:BlockRow
    actions:list[ActionRow]
    before:SnapshotRow
    after:SnapshotRow|None
    previous:int|None
    next:int|None


LivePage.model_rebuild()
