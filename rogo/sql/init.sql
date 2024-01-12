-- sqlite schema for rogo (both client and server)

create table meta (
    key text primary key,
    val text);

insert into meta values ('schema_version', '1.0');


create table servers (
    id integer primary key,
    url text not null unique,
    name text not null,
    info text not null);

insert into servers (url, name, info) values
  ('https://rogo.tangentcode.com/', 'tangentcode',
   'The original rogo server at tangentcode.com');


create table users (
    id integer primary key,
    ts datetime not null default current_timestamp,
    sid integer not null references servers,
    authid text not null, -- references external authentication provider (firebase)
    username text not null,
    unique (sid, username),
    unique (sid, authid));


create table tokens (
    id integer primary key,
    ts datetime not null default current_timestamp,
    uid integer not null references users,
    jwt text not null);


create table challenges (
    id integer primary key,
    sid  integer not null references servers,
    name  text,
    title text,
    unique (sid, name));


create table attempts (
    id integer primary key,
    uid integer not null references users,
    chid integer not null references challenges,
    ts datetime not null default current_timestamp,
    code text unique not null,
    name text,
    done integer,
    is_private integer not null default 0,
    state text not null default 'build',
    lang text,
    repo text);


create table progress (
    id integer primary key,
    aid integer not null references attempts,
    tid integer not null references tests,
    ts integer not null,
    vcs_ref text);


create table tests (
    id integer primary key,
    chid integer not null references challenges,
    name text not null,
    head text not null,
    body text not null,
    ilines text not null,
    olines integer not null);
