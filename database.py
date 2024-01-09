import sqlite3

SDB_PATH = 'rogo.sdb'  # TODO: make this configurable


def fetch(sql):
    """fetch a relation from the database"""
    dbc = sqlite3.connect(SDB_PATH)
    cur = dbc.execute(sql)
    cols = [x[0] for x in cur.description]
    return [{k: v for k, v in zip(cols, vals)}
            for vals in cur.fetchall()]
