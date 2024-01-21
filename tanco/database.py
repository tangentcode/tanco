import os
import sqlite3

from . import model as m

SDB_PATH = os.environ.get('TANCO_SDB_PATH')
if not SDB_PATH:
    SDB_PATH = os.path.expanduser('~/.tanco.sdb')


def ensure_sdb():
    if not os.path.exists(SDB_PATH):
        print('Creating database at', SDB_PATH)
        import tanco
        sql = open(os.path.join(*tanco.__path__, 'sql', 'init.sql')).read()
        dbc = begin()
        dbc.executescript(sql)
        dbc.commit()


def query(sql, *a, **kw) -> list[dict]:
    """fetch a relation from the database"""
    dbc = sqlite3.connect(SDB_PATH)
    cur = dbc.execute(sql, *a, **kw)
    cols = [x[0] for x in cur.description]
    return [{k: v for k, v in zip(cols, vals)}
            for vals in cur.fetchall()]


def commit(sql, *a, **kw) -> int | None:
    """commit a transaction to the database"""
    dbc = begin()
    cur = dbc.execute(sql, *a, **kw)
    dbc.commit()
    return cur.lastrowid


def begin() -> sqlite3.Connection:
    """return a connection so you can begin a transaction"""
    tx = sqlite3.connect(SDB_PATH)
    tx.execute('PRAGMA foreign_keys = ON')
    return tx


def chomp(lines: list[str]) -> list[str]:
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


def get_next_tests(aid: str, uid: int):
    """get the next group of tests for a given attempt"""
    return query("""
        select t.* from (
            select t.chid, t.grp
            from (attempts a left join tests t on a.chid=t.chid)
                left join progress p on a.id=p.aid and t.id=p.tid
            where a.code=(:code) and a.uid = (:uid)
            group by t.grp having count(p.id)=0
            order by t.grp limit 1) as g
        left join tests t on g.chid=t.chid and g.grp=t.grp
        """, {'code': aid, 'uid': uid})


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
    assert rule['kind'] == 'lines', \
        f"don't know how to save {rule['kind']!r} rules"
    commit("""
        update tests set olines = ?
        where name = ?
          and chid = (
            select a.chid from attempts a
            where a.code = ?)
        """, ['\n'.join(rule['data']), test, attempt])


def get_attempt_test(uid, code, test_name):
    rows = query(
        """
        select t.name, t.head, t.body, t.ilines, t.olines
        from attempts a left join tests t on a.chid=t.chid
        where a.code=? and a.uid=? and t.name=?
        """, [code, uid, test_name])
    # the actual output from the test run is the request body (json)
    if not rows:
        raise LookupError(f'attempt: {code}, test: {test_name}')
    return test_from_row(rows[0])


def set_attempt_state(uid, code, transition: m.Transition, failing_test: str = '') -> tuple[m.AttemptState, str]:
    """set the state of an attempt according to transition table"""
    try:
        old = query("""
            select a.id as aid, a.state, t.name as focus
            from attempts a left join tests t on a.focus = t.id
            where a.code=? and a.uid=?""", [code, uid])[0]
    except IndexError:
        raise LookupError(f'attempt: {code}')

    # o: one-letter code for old state:
    # 'sbfcd' start build fix change done (the possible states)
    o = old['state'][0].lower()

    new_focus = None

    # t: one-letter code for transition:
    # 'XPNO' X:tanco-next P=test pass, N=new fail, O=old fail
    match transition:
        case m.Transition.Pass: t = 'P'
        case m.Transition.Next: t = 'X'  # !! what about `tanco next` but no more tests?
        case m.Transition.Fail:
            assert failing_test, 'failing test required for Fail transition'
            row = query("""
                select t.id, count(p.id) > 0 as is_regression
                from attempts a, tests t left join progress p on t.id = p.tid
                where a.id = (:aid) and a.chid = t.chid
                  and a.id = p.aid and t.name = (:test)
                group by t.id""", {'aid': old['aid'], 'test': failing_test})[0]
            new_focus, is_regression = row['id'], row['is_regression']
            t = 'O' if is_regression else 'N'
        case _: raise ValueError(f'unknown transition: {transition}')

    # state machine transition table:
    sm = {'s': {'X': 'b', 'P': 's'},  # they might do "tanco test" from start
          'b': {'P': 'c', 'N': 'b', 'O': 'f'},
          'f': {'O': 'f', 'N': 'b', 'P': 'c'},
          'c': {'X': '?', 'O': 'f', 'P': 'c'},
          'd': {'X': 'd', 'O': 'f', 'P': 'd'}}

    # 's.X:b'  # others can't happen (no test until build state)
    # 's.P:s'  # you pass the 0 tests at the start
    # 'b.X->ERR'
    # 'b.P:c'
    # 'b.N:b'
    # 'b.O:f'
    # 'f.O:f'
    # 'f.N:b'
    # 'f.P:c'
    # 'c.P:c'
    # 'c.N:f'  # really this can't happen because no 'new' test anymore
    # 'c.O:f'  # all tests are old tests
    # 'c.X:(b|d)'
    # 'd.X:d'  # nothing more to do
    # 'd.P:d'  # you ran the tests just to see them pass
    # 'd.O:f'  # you put yourself back in 'change' mode without telling us

    # n: one-letter code for new state (same as codes for o)
    n = sm[o].get(t)
    # print(f"transition: {o}.{t} -> ", n)
    if not n:
        raise ValueError(f'invalid transition: {o}.{t}')
    elif n in 'b?':  # c.X ('tanco next' from 'change' state)
        next_tests = get_next_tests(code, uid)
        if next_tests:
            n = 'b'
            new_focus = next_tests[0]['id']
        else:
            n = 'd'

    new_focus_name = ''
    if new_focus:
        new_focus_name = query('select name from tests where id=?', [new_focus])[0]['name']

    match n:
        case 's': new_state = m.AttemptState.Start
        case 'b': new_state = m.AttemptState.Build
        case 'f': new_state = m.AttemptState.Fix
        case 'c': new_state = m.AttemptState.Change
        case 'd': new_state = m.AttemptState.Done
        case _: raise ValueError(f'unknown state: {n}')

    commit("""
        update attempts set state=(:new_state), focus=(:new_focus)
        where id=(:aid)
        """, {'new_state': new_state.name.lower(),
              'new_focus': new_focus, 'aid': old['aid']})

    return new_state, new_focus_name


def uid_from_tokendata(sid, authid, username):
    rows = query('select id from users where sid=? and authid=?', [sid, authid])
    if rows:
        uid = rows[0]['id']
    else:
        uid = commit("""
          insert into users (sid, authid, username)
          values (?, ?, ?)
          """, [sid, authid, username])
    return uid


def current_state(attempt):
    return query('select state from attempts where code=?',
                 [attempt])[0]['state']


def current_status(attempt):
    try:
        return query("""
            select s.url as server, c.name as challenge, a.state, t.name as focus
            from challenges c, servers s, attempts a left join tests t on a.focus = t.id
            where a.chid = c.id and c.sid = s.id and a.code=?""", [attempt])[0]
    except IndexError:
        raise LookupError(f'attempt: {attempt}')
