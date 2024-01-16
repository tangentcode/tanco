import sqlite3
from . import model as m

SDB_PATH = 'rogo.sdb'  # TODO: make this configurable


def query(sql, *a, **kw):
    """fetch a relation from the database"""
    dbc = sqlite3.connect(SDB_PATH)
    cur = dbc.execute(sql, *a, **kw)
    cols = [x[0] for x in cur.description]
    return [{k: v for k, v in zip(cols, vals)}
            for vals in cur.fetchall()]


def commit(sql, *a, **kw):
    """commit a transaction to the database"""
    dbc = begin()
    cur = dbc.execute(sql, *a, **kw)
    dbc.commit()
    return cur.lastrowid


def begin():
    """return a connection so you can begin a transaction"""
    tx = sqlite3.connect(SDB_PATH)
    tx.execute('PRAGMA foreign_keys = ON')
    return tx


def chomp(lines):
    """remove trailing blank line"""
    if not lines: return []
    return lines[:-1] if lines[-1] == '' else lines


def fetch_challenge(chid: int):
    """fetch a challenge from the database"""
    rows = query('select * from challenges where id=?', [chid])
    if not rows:
        raise LookupError(f'Challenge "{chid}" not found in the database.')
    res = m.Challenge(**rows[0])
    for row in query('select * from tests where chid=?', [chid]):
        res.tests.append(test_from_row(row))
    return res


def test_from_row(row) -> m.TestDescription:
    t = row
    t['ilines'] = chomp(t['ilines'].split('\n'))
    if t['olines'] is not None:
        t['olines'] = chomp(t['olines'].split('\n'))
    return m.TestDescription(**t)


def challenge_from_attempt(aid: str):
    """fetch a challenge from the database"""
    rows = query('select chid from attempts where code=(:code)',
                 {'code': aid})
    if not rows:
        raise LookupError(f'Attempt "{aid}" not found in the database.')
    return fetch_challenge(rows[0]['chid'])


def get_server_id(url):
    """get the server id for a given url"""
    rows = query('select id from servers where url=?', [url])
    if not rows:
        raise LookupError(f'Server "{url}" not found in the database.')
    return rows[0]['id']


def get_next_tests(aid: str):
    """get the next group of tests for a given attempt"""
    return query("""
        select t.* from (
            select t.chid, t.grp
            from (attempts a left join tests t on a.chid=t.chid)
                left join progress p on t.id=p.tid
            where a.code=(:code)
            group by t.grp having count(p.id)=0
            order by t.grp limit 1) as g
        left join tests t on g.chid=t.chid and g.grp=t.grp
        """, {'code': aid})


def save_progress(attempt: str, test: str, _passed: bool):
    """save progress when a test passes"""
    commit("""
      insert into progress (aid, tid)
        select a.id as aid, t.id as tid
        from attempts a, tests t
        where a.chid = t.chid
          and a.code = ? and t.name = ?
        """, [attempt, test])


def save_rule(attempt: str, test: str, rule: dict):
    """save a rule for a test"""
    # TODO: save the rule to the database as json
    # json.dumps(rule)

    # for now, we still have this 'olines' thing
    assert rule['kind'] == 'lines',\
        f"don't know how to save {rule['kind']!r} rules"
    commit("""
        update tests set olines = ?
        where name = ?
          and chid = (
            select a.chid from attempts a
            where a.code = ?)
        """, ['\n'.join(rule['data']), test, attempt])
