begin;

set local lock_timeout = '3s';

do $$
begin
  if (select encode(digest, 'hex') from schema_digest) is distinct from 'cdc8445b25142ddcf777f6a2a72481d3fa4dbf33bb12c7ff1f5792d1eb5b338c' then
    raise exception 'migrate_sizer.sql digest=% expected=cdc8445b25142ddcf777f6a2a72481d3fa4dbf33bb12c7ff1f5792d1eb5b338c', (select encode(digest, 'hex') from schema_digest);
  end if;
end $$;

alter table run add column sizer text check (sizer in ('random', 'catboost', 'mixed'));
update run set sizer = case when picker = 'catboost' then 'mixed' else 'random' end;
alter table run alter column sizer set not null;

create table size_candidate (
  run_id int4 not null references run,
  seq int4 not null,
  actions int2 not null,
  predicted_change float8 not null,
  chosen bool not null,
  primary key (run_id, seq, actions)
);

create table size_model (
  run_id int4 primary key references run,
  pauses int4 not null,
  runs int4 not null,
  seconds float8 not null,
  iterations int4 not null,
  depth int2 not null,
  learning_rate float8 not null,
  loss_function text not null,
  random_seed int4 not null,
  thread_count int2 not null,
  rsm float8 not null,
  l2_leaf_reg float8 not null,
  random_strength float8 not null,
  one_hot_max_size int2 not null,
  max_ctr_complexity int2 not null,
  boosting_type text not null,
  bootstrap_type text not null,
  subsample float8,
  bagging_temperature float8,
  border_count int2 not null,
  leaf_estimation_iterations int2 not null,
  counter_calc_method text not null,
  grow_policy text not null,
  min_data_in_leaf int4,
  max_leaves int4
);

create table size_importance (
  run_id int4 not null references size_model,
  feature text not null,
  importance float8 not null,
  primary key (run_id, feature)
);

update schema_digest set digest = decode('ff13f0647dc2bd509dbcbbb4710c98c59956d323cb31942c649d88840bc57c5d', 'hex');

commit;
