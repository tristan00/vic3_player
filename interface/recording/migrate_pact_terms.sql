begin;
set local lock_timeout = '3s';

do $$
begin
  if (select encode(digest, 'hex') from schema_digest) <> '110ed906ba89d75b5c0b2a89996855a085bfaa6af903cc876d61923218a003a7' then
    raise exception 'Unexpected source schema for pact terms migration';
  end if;
end $$;
create table pact_private (
  run_id int4 not null,
  pact int4 not null,
  seq int4 not null,
  present bool not null,
  start_date game_hours,
  forced_duration int4,
  primary key (run_id, pact, seq),
  foreign key (run_id, pact) references pact,
  foreign key (run_id, seq) references snapshot,
  check (present = (num_nulls(start_date, forced_duration) = 0)),
  check (present or num_nonnulls(start_date, forced_duration) = 0)
);
create function pact_private_at(run int4, at int4) returns table ("pact" int4, "seq" int4, "start_date" game_hours, "forced_duration" int4) language sql stable as $$
  select l.pact, l.seq, l.start_date, l.forced_duration from pact a, lateral (select pact, seq, start_date, forced_duration, present from pact_private t where t.run_id = run and t.pact = a.pact and t.seq <= at order by t.seq desc limit 1) l where a.run_id = run and l.present
$$;
create index pact_private_seq on pact_private using brin (run_id, seq) with (autosummarize = on);
update schema_digest set digest = decode('a3adb8870a20e37007b8d5b0f97295ec1974a7f5019641298963e341b8e69282', 'hex');
commit;
