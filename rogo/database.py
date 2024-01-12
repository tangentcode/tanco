import sqlite3
from .model import Challenge, TestDescription

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
    res = Challenge(**rows[0])
    for t in query('select * from tests where chid=?', [chid]):
        t.pop('id')
        t.pop('chid')
        t['ilines'] = chomp(t['ilines'].split('\n'))
        t['olines'] = chomp(t['olines'].split('\n'))
        res.tests.append(TestDescription(**t))
    return res


def challenge_from_attempt(aid: str):
    """fetch a challenge from the database"""
    rows = query('select chid from attempts where code=?', [aid])
    if not rows:
        raise LookupError(f'Attempt "{aid}" not found in the database.')
    return fetch_challenge(rows[0]['chid'])


def get_server_id(url):
    """get the server id for a given url"""
    rows = query('select id from servers where url=?', [url])
    if not rows:
        raise LookupError(f'Server "{url}" not found in the database.')
    return rows[0]['id']
