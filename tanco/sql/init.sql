-- sqlite schema for tanco (both client and server)

create table meta (
    key text primary key,
    val text);

insert into meta values ('schema_version', '0.1');


create table servers (
    id integer primary key,
    url text not null unique,
    name text not null,
    info text not null);

insert into servers (url, name, info) values
  ('https://tanco.tangentcode.com/', 'tangentcode',
   'The original tanco server at tangentcode.com');


create table users (
    id integer primary key,
    ts datetime not null default current_timestamp,
    sid integer not null references servers,
    authid text not null, -- references external authentication provider (firebase)
    username text not null,
    unique (sid, username),
    unique (sid, authid));


create table sessions (
    id integer primary key,
    ts datetime not null default current_timestamp,
    skey text not null unique,
    uid integer not null references users,
    sid integer not null references servers,
    seen datetime not null default current_timestamp,
    data text);


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
    done datetime default null,
    state text default 'start'
          check (state in ('start','build','change','fix','done')),
    focus integer references tests(id),
    is_private integer not null default 0,
    lang text,
    repo text);


create table progress (
    id integer primary key,
    aid integer not null references attempts,
    tid integer not null references tests,
    ts datetime not null default current_timestamp,
    ver text);


create table tests (
    id integer primary key,
    chid integer not null references challenges,
    grp integer not null default 0,  -- group of tests (one feature)
    ord integer not null default 0,  -- order within group
    name text not null,
    head text not null,
    body text not null,
    ilines text not null,
    olines text,
    unique(chid, name),
    unique(chid, grp, ord));
