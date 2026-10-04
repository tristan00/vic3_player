alter table pick_model
  add column grow_policy text,
  add column min_data_in_leaf int4,
  add column max_leaves int4;
