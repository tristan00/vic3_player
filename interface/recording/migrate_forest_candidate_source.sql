begin;

set local lock_timeout = '3s';

do $$
begin
  if (select encode(digest, 'hex') from schema_digest) is distinct from 'ff4786080ac20bda84ee377576e98f595ee41b6e4ec98c42077a5e6ab6ac9d96' then
    raise exception 'migrate_forest_candidate_source.sql digest=% expected=ff4786080ac20bda84ee377576e98f595ee41b6e4ec98c42077a5e6ab6ac9d96', (select encode(digest, 'hex') from schema_digest);
  end if;
end $$;

alter table forest_candidate drop column source;

update schema_digest set digest = decode('d40e422e5dcaebec0d40e05cf722410e2002eef1fe4ae885640ddfaf203daa7a', 'hex');

commit;
