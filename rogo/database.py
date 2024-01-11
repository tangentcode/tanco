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
    dbc = sqlite3.connect(SDB_PATH)
    cur = dbc.execute(sql, *a, **kw)
    dbc.commit()
    return cur.lastrowid


def begin():
    """return a connection so you can begin a transaction"""
    tx = sqlite3.connect(SDB_PATH)
    return tx


def chomp(lines):
    """remove trailing blank line"""
    if not lines: return []
    return lines[:-1] if lines[-1] == '' else lines


def fetch_challenge(url: str):
    """fetch a challenge from the database"""
    rows = query('select * from challenges where url=?', [url])
    if not rows:
        raise LookupError(f'Challenge "{url}" not found in the database.')
    row = rows[0]
    chid = row.pop('id')
    res = Challenge(**row)
    for t in query('select * from tests where chid=?', [chid]):
        t.pop('id')
        t.pop('chid')
        t['ilines'] = chomp(t['ilines'].split('\n'))
        t['olines'] = chomp(t['olines'].split('\n'))
        res.tests.append(TestDescription(**t))
    return res
