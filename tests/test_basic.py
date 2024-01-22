import os
import pathlib
import unittest

TESTS_PATH = pathlib.Path(__file__).parent
TANCO_SDB_PATH = TESTS_PATH / 'tanco.sdb'
os.environ['TANCO_SDB_PATH'] = str(TANCO_SDB_PATH)
TANCO_SERVER = 'fake://invalid url/'

import tanco.client  # noqa: E402
import tanco.database  # noqa: E402

class BasicTest(unittest.TestCase):
    def setUp(self) -> None:
        TANCO_SDB_PATH.unlink(missing_ok=True)
        tanco.database.ensure_sdb()
        with tanco.database.begin() as conn:
            cur = conn.execute('insert into servers (url, name, info) values (?, ?, ?)',
                    (TANCO_SERVER, 'fakeserver', 'fake'))
            sid = cur.lastrowid
            cur = conn.execute('insert into users (sid, authid, username) values (?, ?, ?)',
                    (sid, 'fakeauthid', 'fakeuser'))
            uid = cur.lastrowid
            conn.execute('insert into tokens (uid, jwt) values (?, ?)', (uid, 'fakejwt'))

    def tearDown(self) -> None:
        TANCO_SDB_PATH.unlink()

    def test_auth(self) -> None:
        client = tanco.client.TancoClient(TANCO_SERVER)
        assert client.whoami()['username'] == 'fakeuser'
