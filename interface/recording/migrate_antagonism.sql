begin;

set local lock_timeout = '3s';

do $$
begin
  if (select encode(digest, 'hex') from schema_digest) is distinct from '5e29e5d60e94a06b0be9f7acfbd5da219dd4b5112fac43a53bc15632f436cc4b' then
    raise exception 'Unexpected source schema for antagonism migration';
  end if;
end $$;

alter table run add column antagonism float8 check (antagonism between 0 and 1);

update schema_digest set digest = decode('859b135885d7df8cbe49df65fcfa34d7b8b7935937df2fb89f03d62a013936e3', 'hex');

commit;
