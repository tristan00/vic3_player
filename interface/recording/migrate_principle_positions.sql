begin;
set local lock_timeout = '3s';

do $$
begin
  if (select encode(digest, 'hex') from schema_digest) is distinct from 'a3adb8870a20e37007b8d5b0f97295ec1974a7f5019641298963e341b8e69282' then
    raise exception 'Unexpected source schema for principle positions migration';
  end if;
end $$;
alter table power_bloc_adopted_principle add column position int2;
alter table power_bloc_adopted_principle add check (present or num_nonnulls(position) = 0);
drop function power_bloc_adopted_principle_at(int4, int4);
create function power_bloc_adopted_principle_at(run int4, at int4) returns table ("power_bloc" int4, "power_bloc_principle" int2, "seq" int4, "position" int2) language sql stable as $$
  select l.power_bloc, l.power_bloc_principle, l.seq, l.position from power_bloc a, lateral (select distinct on (power_bloc_principle) power_bloc, power_bloc_principle, seq, position, present from power_bloc_adopted_principle t where t.run_id = run and t.power_bloc = a.power_bloc and t.seq <= at order by power_bloc_principle desc, t.seq desc) l where a.run_id = run and l.present
$$;
update schema_digest set digest = decode('280705c4cb77f8b0a94196bcc19fcacbf98a44fc267b43d5fd8127dbe8d26bc8', 'hex');
commit;
