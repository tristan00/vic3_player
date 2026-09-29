alter table run add foreign key (run_id, player_country) references country deferrable initially deferred;

create view run_lost as
  select run_id, kind, started_at, heartbeat_at, now() - heartbeat_at as silent_for
  from run where ended_at is null and heartbeat_at < now() - interval '0.5 second';

create view run_stalled as
  select run_id, kind, started_at, progress_step, now() - progress_at as stalled_for
  from run where ended_at is null and progress_at < now() - interval '5 seconds';

create view run_late_flag as
  select run_id, kind, end_reason, game_exited_at, ended_at, ended_at - game_exited_at as flag_delay
  from run where end_reason = 'game_crashed' and (game_exited_at is null or ended_at - game_exited_at > interval '1 second');

create index pop_history_location on pop_history (run_id, location, seq);
create index building_history_state on building_history (run_id, state, seq);
create index state_history_country on state_history (run_id, country, seq);
create index character_history_country on character_history (run_id, country, seq);

create function run_numbering() returns trigger language plpgsql as $$
begin
  if exists (select 1 from run having count(*) <> max(run_id)) then
    raise exception 'run ids must run from 1 without a gap';
  end if;
  return null;
end $$;

create constraint trigger run_numbering after insert or delete or update of run_id on run
  deferrable initially deferred for each row execute function run_numbering();
alter table run enable always trigger run_numbering;

create function renumber_run(old int4, new int4) returns void language plpgsql set session_replication_role = replica as $$
declare
  target record;
begin
  for target in select c.relname from pg_class c join pg_attribute a on a.attrelid = c.oid
                 where c.relnamespace = 'public'::regnamespace and c.relkind = 'r' and a.attname = 'run_id' and c.relname <> 'run' loop
    execute format('update %I set run_id = $2 where run_id = $1', target.relname) using old, new;
  end loop;
  update smac_observation set observed_run = new where observed_run = old;
  update run set run_id = new where run_id = old;
end $$;

create function delete_run(doomed int4) returns void language plpgsql set session_replication_role = replica as $$
declare
  target record;
  later int4;
begin
  for target in select c.relname from pg_class c join pg_attribute a on a.attrelid = c.oid
                 where c.relnamespace = 'public'::regnamespace and c.relkind = 'r' and a.attname = 'run_id' and c.relname <> 'run' loop
    execute format('delete from %I where run_id = $1', target.relname) using doomed;
  end loop;
  delete from smac_observation where observed_run = doomed;
  delete from run where run_id = doomed;
  for later in select run_id from run where run_id > doomed order by run_id loop
    perform renumber_run(later, later - 1);
  end loop;
end $$;
