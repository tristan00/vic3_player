begin;
do $$
begin
  if (select encode(digest, 'hex') from schema_digest) <> 'f800b9df12d8632f3a0d8972288e7e761583e1663a06c2a86234d21ea89ebce9' then
    raise exception 'Unexpected source schema for politics and culture migration';
  end if;
end $$;
alter table run add column ideology_uniformity float8 check (ideology_uniformity between 0 and 1);
alter table run add column primary_culture_share float8 check (primary_culture_share between 0 and 1);
update schema_digest set digest = decode('9cb47bd212a9781e83bd74564ff8ff2c1eeb247e45bc756780630cc6c65f0f96', 'hex');
commit;
