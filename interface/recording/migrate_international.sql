begin;
do $$
begin
  if (select encode(digest, 'hex') from schema_digest) <> 'e18f43ce2bcb62e438ee0bc00a8858ea683d8dfcf3d29ba7feef9a06216594fc' then
    raise exception 'migrate_international.sql digest=% expected=e18f43ce2bcb62e438ee0bc00a8858ea683d8dfcf3d29ba7feef9a06216594fc', (select encode(digest, 'hex') from schema_digest);
  end if;
end $$;
alter table run add column interconnectedness float8 check (interconnectedness between 0 and 1);
update schema_digest set digest = decode('110ed906ba89d75b5c0b2a89996855a085bfaa6af903cc876d61923218a003a7', 'hex');
commit;
