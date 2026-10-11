begin;

set local lock_timeout = '3s';

do $$
begin
  if (select encode(digest, 'hex') from schema_digest) <> '280705c4cb77f8b0a94196bcc19fcacbf98a44fc267b43d5fd8127dbe8d26bc8' then
    raise exception 'migrate_law_enactment.sql digest=% expected=280705c4cb77f8b0a94196bcc19fcacbf98a44fc267b43d5fd8127dbe8d26bc8', (select encode(digest, 'hex') from schema_digest);
  end if;
end $$;

alter table law_private add column enactment_phase int4,
  add column checkpoint_progress float8,
  add column enactment_setbacks int4,
  add column advance_chance float8,
  add column debate_chance float8,
  add column stall_chance float8;

alter table law_private drop constraint law_private_check1;

alter table law_private add constraint law_private_check1 check (present or num_nonnulls(checkpoint_result, replacing_law_type, enactment_start_date, chance, enactment_phase, checkpoint_progress, enactment_setbacks, advance_chance, debate_chance, stall_chance) = 0);

drop function law_private_at(int4,int4);

create function law_private_at(run int4, at int4) returns table ("law" int4, "seq" int4, "checkpoint_result" int2, "replacing_law_type" int2, "enactment_start_date" game_hours, "chance" float8, "enactment_phase" int4, "checkpoint_progress" float8, "enactment_setbacks" int4, "advance_chance" float8, "debate_chance" float8, "stall_chance" float8) language sql stable as $$
  select l.law, l.seq, l.checkpoint_result, l.replacing_law_type, l.enactment_start_date, l.chance, l.enactment_phase, l.checkpoint_progress, l.enactment_setbacks, l.advance_chance, l.debate_chance, l.stall_chance from law a, lateral (select law, seq, checkpoint_result, replacing_law_type, enactment_start_date, chance, enactment_phase, checkpoint_progress, enactment_setbacks, advance_chance, debate_chance, stall_chance, present from law_private t where t.run_id = run and t.law = a.law and t.seq <= at order by t.seq desc limit 1) l where a.run_id = run and l.present
$$;

update schema_digest set digest = decode('5e29e5d60e94a06b0be9f7acfbd5da219dd4b5112fac43a53bc15632f436cc4b', 'hex');

commit;
