alter table run add foreign key (run_id, player_country) references country deferrable initially deferred;

create view run_lost as
  select run_id, kind, started_at, heartbeat_at, now() - heartbeat_at as silent_for
  from run where ended_at is null and heartbeat_at < now() - interval '0.5 second';

create view action_run_outcome as
  select l.run_id, l.action, r.started_at,
         case when g.run_id is null then 'attached' when g.world_file = 'vanilla' then 'vanilla_' || d.name else g.world_file end as world,
         count(*) filter (where l.status = 'verified') as verified,
         count(*) filter (where l.status = 'unverified') as unverified,
         count(*) filter (where l.status in ('invalid', 'no_object', 'no_effect', 'ui_leftover')) as failed,
         count(*) filter (where l.status = 'raced') as raced
  from loop_action l join run r using (run_id) left join run_generated g using (run_id) left join country_definition d on d.country_definition = g.tag
  group by l.run_id, l.action, r.started_at, g.run_id, g.world_file, d.name;

create view action_verification as
  with recent as (
    select * from (select o.*, row_number() over (partition by action order by run_id desc) as recency from action_run_outcome o) ranked
    where recency <= 3)
  select a.action as action_id, a.name as action,
         (select count(*) from action_run_outcome o where o.action = a.action) as runs,
         coalesce(sum(t.verified), 0) as verified, coalesce(sum(t.unverified), 0) as unverified, coalesce(sum(t.failed), 0) as failed,
         count(distinct t.world) filter (where t.verified > 0) as worlds,
         coalesce(sum(t.verified), 0) >= 3 and count(distinct t.world) filter (where t.verified > 0) >= 2
           and coalesce(sum(t.verified), 0) >= 0.95 * (coalesce(sum(t.verified), 0) + coalesce(sum(t.failed), 0)) as verified_by_standard
  from catalogue_action ca join action a using (action) left join recent t on t.action = a.action
  group by a.action, a.name;

create view verification_summary as
  select count(*) filter (where verified_by_standard) as verified_actions, count(*) as catalogue_actions,
         count(*) filter (where runs = 0) as never_attempted
  from action_verification;

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
