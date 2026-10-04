alter table run drop constraint run_picker_check;
alter table run add constraint run_picker_check check (picker in ('first','catboost','catboost_piecewise'));
alter table pick_model
  add column model_kind text not null default 'histogram' check (model_kind in ('histogram','row')),
  add column training_rows int4,
  add column max_ctr_complexity int2,
  add column boosting_type text,
  add column bootstrap_type text,
  add column subsample float8,
  add column bagging_temperature float8,
  add column border_count int2,
  add column leaf_estimation_iterations int2,
  add column counter_calc_method text;
