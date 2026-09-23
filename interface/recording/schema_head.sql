create domain game_hours as int4;

create table schema_digest (
  id bool primary key default true check (id),
  digest bytea not null
);
