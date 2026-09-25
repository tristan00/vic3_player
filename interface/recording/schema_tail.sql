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

create function delete_run(doomed int4) returns void language plpgsql set session_replication_role = replica as $$
declare
  target record;
begin
  for target in select c.relname from pg_class c join pg_attribute a on a.attrelid = c.oid
                 where c.relnamespace = 'public'::regnamespace and c.relkind = 'r' and a.attname = 'run_id' and c.relname <> 'run' loop
    execute format('delete from %I where run_id = $1', target.relname) using doomed;
  end loop;
  delete from run where run_id = doomed;
end $$;
