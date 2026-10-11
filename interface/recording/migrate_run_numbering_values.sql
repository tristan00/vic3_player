begin;

set local lock_timeout = '3s';

do $$
begin
  if (select encode(digest, 'hex') from schema_digest) is distinct from '1745b0b5a7b69e5e48844975599ffa3c568612d96d034e9cce1f98d13945d472' then
    raise exception 'migrate_run_numbering_values.sql digest=% expected=1745b0b5a7b69e5e48844975599ffa3c568612d96d034e9cce1f98d13945d472', (select encode(digest, 'hex') from schema_digest);
  end if;
end $$;

create or replace function run_numbering() returns trigger language plpgsql as $$
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

update schema_digest set digest = decode('cdc8445b25142ddcf777f6a2a72481d3fa4dbf33bb12c7ff1f5792d1eb5b338c', 'hex');

commit;
