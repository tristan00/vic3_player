begin;
set local lock_timeout = '3s';

do $$
begin
  if (select encode(digest, 'hex') from schema_digest) <> 'a29a5ddcd264e0117235ec8bbf259dd47f0b90b31bf1b89f81f8e159db6c9dea' then
    raise exception 'Unexpected source schema for battle log migration';
  end if;
end $$;
create table battle_start (
  run_id int4 not null,
  n int4 not null,
  seq int4 not null,
  date game_hours,
  battle int4,
  naval_battle int4,
  state int4,
  front int4,
  province int4,
  attacker_country int4,
  defender_country int4,
  attacker int4,
  defender int4,
  attacker_manpower int4,
  defender_manpower int4,
  naval bool not null,
  primary key (run_id, n),
  foreign key (run_id, seq) references snapshot,
  foreign key (run_id, battle) references battle,
  foreign key (run_id, state) references state,
  foreign key (run_id, front) references front,
  foreign key (run_id, province) references province,
  foreign key (run_id, attacker_country) references country,
  foreign key (run_id, defender_country) references country,
  foreign key (run_id, attacker) references character,
  foreign key (run_id, defender) references character
);
create table battle_unit (
  run_id int4 not null,
  n int4 not null,
  seq int4 not null,
  date game_hours,
  battle int4 not null,
  stage text not null,
  combat_unit int4 not null,
  country int4 not null,
  side text,
  manpower int4 not null,
  demoralized int4 not null,
  morale float8 not null,
  offense float8 not null,
  defense float8 not null,
  engaged bool not null,
  primary key (run_id, n),
  foreign key (run_id, seq) references snapshot,
  foreign key (run_id, battle) references battle,
  check (stage in ('start', 'end')),
  foreign key (run_id, combat_unit) references combat_unit,
  foreign key (run_id, country) references country,
  check (side in ('attacker', 'defender'))
);
create table battle_ship (
  run_id int4 not null,
  n int4 not null,
  seq int4 not null,
  date game_hours,
  naval_battle int4 not null,
  stage text not null,
  ship int4 not null,
  fleet int4,
  country int4 not null,
  side text,
  hit_points float8 not null,
  crew int4 not null,
  primary key (run_id, n),
  foreign key (run_id, seq) references snapshot,
  check (stage in ('start', 'end')),
  foreign key (run_id, ship) references ship,
  foreign key (run_id, fleet) references formation,
  foreign key (run_id, country) references country,
  check (side in ('attacker', 'defender'))
);
create index battle_start_seq on battle_start using brin (run_id, seq) with (autosummarize = on);
create index battle_unit_seq on battle_unit using brin (run_id, seq) with (autosummarize = on);
create index battle_ship_seq on battle_ship using brin (run_id, seq) with (autosummarize = on);
alter table battle_result add column naval_battle int4, add column winner_role text, add column attacker_manpower int4, add column defender_manpower int4,
  add check (winner_role in ('attacker', 'defender'));
alter table building_ownership_history drop constraint building_ownership_history_owner_kind_check,
  add check (owner_kind in ('country', 'self', 'manor_house', 'financial_district', 'company', 'company_regional_headquarter', 'vanished_building'));
update building_ownership_history set owner_kind = 'vanished_building' where owner_kind = 'company' and owner_company is null;
alter table building_history drop constraint building_history_slave_basket_fkey, drop constraint building_history_privatization_requested_fkey;
drop table slave_basket;
drop table privatization_request;
drop function treaty_at(int4, int4);
alter table treaty_history drop constraint treaty_history_check, drop constraint treaty_history_check1, drop column withdrawn_by,
  add check (present = (num_nulls(first_country, second_country, binding_period, withdrawn) = 0)),
  add check (present or num_nonnulls(first_country, second_country, entered_into_force_on, binding_period, withdrawn) = 0);
drop table treaty_side;
create function treaty_at(run int4, at int4) returns table ("treaty" int4, "seq" int4, "first_country" int4, "second_country" int4, "entered_into_force_on" game_hours, "binding_period" int4, "withdrawn" bool) language sql stable as $$
  select l.treaty, l.seq, l.first_country, l.second_country, l.entered_into_force_on, l.binding_period, l.withdrawn from treaty a, lateral (select treaty, seq, first_country, second_country, entered_into_force_on, binding_period, withdrawn, present from treaty_history t where t.run_id = run and t.treaty = a.treaty and t.seq <= at order by t.seq desc limit 1) l where a.run_id = run and l.present
$$;
drop view event_answer_target;
drop view event_answer_effect;
drop view event_answer;
drop function event_at(int4, int4);
alter table event_history drop constraint event_history_check1, drop column status,
  add check (present or num_nonnulls(event_type, origin_country) = 0);
drop table event_status;
create function event_at(run int4, at int4) returns table ("event" int4, "seq" int4, "event_type" int2, "origin_country" int4) language sql stable as $$
  select l.event, l.seq, l.event_type, l.origin_country from event a, lateral (select event, seq, event_type, origin_country, present from event_history t where t.run_id = run and t.event = a.event and t.seq <= at order by t.seq desc limit 1) l where a.run_id = run and l.present
$$;
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
update schema_digest set digest = decode('ff76d96788a07bb19ce33945bc22d43ddef2fb192baddf54c1ebd558acfd2a3d', 'hex');
commit;
