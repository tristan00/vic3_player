begin;
do $$
begin
  if (select encode(digest, 'hex') from schema_digest) <> '01800c43f1ee5ba3f09407108c96ecef6a9b4feae50c642691a8d1301c2a6001' then
    raise exception 'Unexpected source schema for world controls migration';
  end if;
end $$;
alter table run add column tech_variation float8;
alter table run add column country_economy float8;
alter table run add column local_economy float8;
alter table run add column source_regions int2;
alter table run drop constraint run_check6;
alter table run add constraint run_check6 check (kind = 'mini' or copies is null);
update schema_digest set digest = decode('f800b9df12d8632f3a0d8972288e7e761583e1663a06c2a86234d21ea89ebce9', 'hex');
commit;
