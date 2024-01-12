-- sqlite schema for rogo (both client and server)

create table meta (
    key text not null unique,
    val text);

insert into meta values ('schema_version', '1.0');


create table servers (
    url text not null unique,
    name text not null,
    info text not null);

insert into servers values
  ('https://rogo.tangentcode.com/', 'tangentcode',
   'The original rogo server at tangentcode.com');


create table users (
    sid integer not null references servers (rowid),
    authid text, -- references external authentication provider (firebase)
    username text not null);


create table tokens (
    uid integer not null references users (rowid),
    jwt text not null,
    ts integer not null );


create table challenges (
    sid  integer not null references servers (rowid),
    name  text unique,
    title text,
    url   text );


create table attempts (
    uid integer not null references users (rowid),
    chid integer not null references challenges (rowid),
    ts integer not null,
    hash text unique,
    done integer,
    is_private integer,
    state text,
    lang text,
    repo text);


create table progress (
    aid integer not null references attempts (rowid),
    tid integer not null references tests (rowid),
    ts integer not null,
    vcs_ref text);


create table tests (
    chid integer not null references challenges (rowid),
    name text not null,
    head text not null,
    body text not null,
    ilines text not null,
    olines integer not null);
