begin;
set local lock_timeout = '3s';

do $$
begin
  if (select encode(digest, 'hex') from schema_digest) <> '76c97eadcdb7ad1904e0636b6112f77f34d00d5ff16ae8e21d80031a369576e7' then
    raise exception 'migrate_conflict_log.sql digest=% expected=76c97eadcdb7ad1904e0636b6112f77f34d00d5ff16ae8e21d80031a369576e7', (select encode(digest, 'hex') from schema_digest);
  end if;
end $$;
create table battle_result (
  run_id int4 not null,
  n int4 not null,
  seq int4 not null,
  date game_hours,
  year int2 not null,
  month int2 not null,
  winner int4 not null,
  loser int4,
  state int4,
  attacker int4,
  defender int4,
  battle int4,
  empty bool not null,
  naval bool not null,
  primary key (run_id, n),
  foreign key (run_id, seq) references snapshot,
  foreign key (run_id, winner) references country,
  foreign key (run_id, loser) references country,
  foreign key (run_id, state) references state,
  foreign key (run_id, attacker) references character,
  foreign key (run_id, defender) references character,
  foreign key (run_id, battle) references battle
);
create table war_event (
  run_id int4 not null,
  n int4 not null,
  seq int4 not null,
  date game_hours,
  year int2 not null,
  month int2 not null,
  kind text not null,
  country int4 not null,
  target_country int4,
  primary key (run_id, n),
  foreign key (run_id, seq) references snapshot,
  check (kind in ('wargoal_enforced', 'capitulation', 'peace_signed', 'war_end')),
  foreign key (run_id, country) references country,
  foreign key (run_id, target_country) references country
);
create index battle_result_seq on battle_result using brin (run_id, seq) with (autosummarize = on);
create index war_event_seq on war_event using brin (run_id, seq) with (autosummarize = on);
alter table formation_status add column current_location_type int2, add column target_location_type int2,
  add foreign key (current_location_type) references scope_type, add foreign key (target_location_type) references scope_type;
drop function formation_status_at(int4, int4);
create function formation_status_at(run int4, at int4) returns table ("formation" int4, "seq" int4, "province" int4, "current_location" int4, "target_location" int4, "naval_mission" int4, "x" float8, "y" float8, "organization" float8, "sea_presence" float8, "supply" float8, "delivered_supply" float8, "supply_ships" int4, "mobilized" bool, "raised_conscripts" bool, "current_location_type" int2, "target_location_type" int2) language sql stable as $$
  select l.formation, l.seq, l.province, l.current_location, l.target_location, l.naval_mission, l.x, l.y, l.organization, l.sea_presence, l.supply, l.delivered_supply, l.supply_ships, l.mobilized, l.raised_conscripts, l.current_location_type, l.target_location_type from formation a, lateral (select present from formation_history h where h.run_id = run and h.formation = a.formation and h.seq <= at order by h.seq desc limit 1) o, lateral (select formation, seq, province, current_location, target_location, naval_mission, x, y, organization, sea_presence, supply, delivered_supply, supply_ships, mobilized, raised_conscripts, current_location_type, target_location_type from formation_status t where t.run_id = run and t.formation = a.formation and t.seq <= at order by t.seq desc limit 1) l where a.run_id = run and o.present
$$;
update schema_digest set digest = decode('a29a5ddcd264e0117235ec8bbf259dd47f0b90b31bf1b89f81f8e159db6c9dea', 'hex');
commit;
