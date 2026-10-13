begin;

set local lock_timeout = '3s';

do $$
begin
  if (select encode(digest, 'hex') from schema_digest) is distinct from 'ff13f0647dc2bd509dbcbbb4710c98c59956d323cb31942c649d88840bc57c5d' then
    raise exception 'migrate_forest_initializer.sql digest=% expected=ff13f0647dc2bd509dbcbbb4710c98c59956d323cb31942c649d88840bc57c5d', (select encode(digest, 'hex') from schema_digest);
  end if;
end $$;

alter table smac_proposal rename to forest_proposal;
alter table smac_observation rename to forest_observation;
alter table smac_candidate rename to forest_candidate;
alter table smac_importance rename to forest_importance;

do $$
declare
  found record;
begin
  for found in select conrelid::regclass as owner, conname from pg_constraint
               where connamespace = 'public'::regnamespace and conname like 'smac\_%' loop
    execute format('alter table %s rename constraint %I to %I', found.owner, found.conname, 'forest' || substr(found.conname, 5));
  end loop;
end $$;

update advisor set name = 'random_forest_weighting' where name = 'random_smac_weighting';

create or replace function renumber_run(old int4, new int4) returns void language plpgsql set session_replication_role = replica as $$
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

create or replace function delete_run(doomed int4) returns void language plpgsql set session_replication_role = replica as $$
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

update schema_digest set digest = decode('ff4786080ac20bda84ee377576e98f595ee41b6e4ec98c42077a5e6ab6ac9d96', 'hex');

commit;
