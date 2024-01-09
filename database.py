import sqlite3

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
