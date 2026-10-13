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
declare
  runs int8;
  last int4;
begin
  select count(*), max(run_id) into runs, last from run;
  if runs <> last then
    raise exception 'run_numbering runs=% last=%', runs, last;
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
  update forest_observation set observed_run = new where observed_run = old;
  update svr_observation set observed_run = new where observed_run = old;
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
  delete from forest_observation where observed_run = doomed;
  delete from svr_observation where observed_run = doomed;
  delete from run where run_id = doomed;
  for later in select run_id from run where run_id > doomed order by run_id loop
    perform renumber_run(later, later - 1);
  end loop;
end $$;

create view event_answer as
select la.run_id, la.n, la.before_seq as seq, la.status, et.event_type, et.name as event, o.option, d.name as option_name, o.visible_position,
       o.default_option, d.has_trigger, o.text, o.description,
       (select count(*) from event_option_at(la.run_id, la.before_seq) x where x.event = o.event and x.enabled and x.visible_position is not null) as options_offered,
       e.origin_country
from loop_action la
join action a on a.action = la.action and a.name = 'choose_event_option'
join run r on r.run_id = la.run_id
join loop_action_param pe on pe.run_id = la.run_id and pe.n = la.n and pe.name = 'event'
join loop_action_param po on po.run_id = la.run_id and po.n = la.n and po.name = 'option'
join event_type et on et.name = pe.text_value
join event_at(la.run_id, la.before_seq) e on e.event_type = et.event_type
join event_option_at(la.run_id, la.before_seq) o on o.event = e.event and o.visible_position = po.integer_value
join event_definition_option d on d.ruleset_id = r.ruleset_id and d.event_type = et.event_type and d.option = o.option;

create view event_answer_effect as
select w.run_id, w.n, w.event, w.option_name, f.position, f.effect, f.detail
from event_answer w
join run r on r.run_id = w.run_id
join event_definition_option_effect f on f.ruleset_id = r.ruleset_id and f.event_type = w.event_type and f.option = w.option;

create view event_answer_target as
select w.run_id, w.n, w.event, w.option_name, k.name as target, s.name as scope, t.scope_target
from event_answer w
join event_at(w.run_id, w.seq) e on e.event_type = w.event_type
join event_target_at(w.run_id, w.seq) t on t.event = e.event
join localization_key k on k.localization_key = t.name_key
join scope_type s on s.scope_type = t.scope_type;
