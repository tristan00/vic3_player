begin;

set local lock_timeout = '3s';

do $$
begin
  if (select encode(digest, 'hex') from schema_digest) is distinct from 'd40e422e5dcaebec0d40e05cf722410e2002eef1fe4ae885640ddfaf203daa7a' then
    raise exception 'migrate_miniworld_knobs.sql digest=% expected=d40e422e5dcaebec0d40e05cf722410e2002eef1fe4ae885640ddfaf203daa7a', (select encode(digest, 'hex') from schema_digest);
  end if;
end $$;

alter table run drop constraint run_check, drop constraint run_check1, drop constraint run_check4;
alter table run drop column modernity, drop column copies, drop column military, drop column source_regions, drop column random_ideology_share,
  drop column primary_culture_share, drop column interconnectedness, drop column antagonism;
alter table run add column concentration float8 check (concentration > 0), add column landmasses int2 check (landmasses >= 1), add column climate float8 check (climate between 0 and 1),
  add column relief float8 check (relief >= 0), add column density float8 check (density > 0), add check (diversity >= 0),
  add column diplomacy float8 check (diplomacy between 0 and 1), add column ideology float8 check (ideology between 0 and 1),
  add check ((kind = 'mini') = (num_nonnulls(world_seed, countries, states, pop, concentration, landmasses, climate, relief, density, diversity, diplomacy, ideology) = 12)),
  add check ((kind = 'vanilla') = (num_nulls(world_seed, countries, states, pop, concentration, landmasses, climate, relief, density, diversity, diplomacy, ideology) = 12));

update schema_digest set digest = decode('461540b90e913c6cd089ed554645f9336ed1f683bada6e2fb7434e00b68aa831', 'hex');

commit;
