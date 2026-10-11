begin;

set local lock_timeout = '3s';

do $$
begin
  if (select encode(digest, 'hex') from schema_digest) is distinct from 'ff76d96788a07bb19ce33945bc22d43ddef2fb192baddf54c1ebd558acfd2a3d' then
    raise exception 'Unexpected source schema for random ideology share migration';
  end if;
end $$;

alter table run rename column ideology_uniformity to random_ideology_share;
alter table run rename constraint run_ideology_uniformity_check to run_random_ideology_share_check;

update schema_digest set digest = decode('1745b0b5a7b69e5e48844975599ffa3c568612d96d034e9cce1f98d13945d472', 'hex');

commit;
