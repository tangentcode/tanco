import os
import pathlib
import tempfile
import unittest

TESTS_PATH = pathlib.Path(__file__).parent
TANCO_SDB_PATH = TESTS_PATH / 'tanco.sdb'
os.environ['TANCO_SDB_PATH'] = str(TANCO_SDB_PATH)
TANCO_SERVER = 'fake://invalid url/'

import tanco.client  # noqa: E402
import tanco.database  # noqa: E402
import tanco.orgtest  # noqa: E402

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


class OrgTestParserTest(unittest.TestCase):

    def _parse_org(self, content):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.org', delete=False) as f:
            f.write(content)
            f.flush()
            try:
                return tanco.orgtest.read_challenge(f.name)
            finally:
                os.unlink(f.name)

    def test_invalid_test_name_rejected(self):
        org = (
            '#+tanco-format: 0.2\n'
            '#+name: test-challenge\n'
            '** TEST foo.?? : this test name is bad\n'
            '#+begin_src\n'
            '> q\n'
            '#+end_src\n'
        )
        with self.assertRaises(ValueError, msg='should reject test name with invalid characters'):
            self._parse_org(org)

    def test_valid_test_names_accepted(self):
        org = (
            '#+tanco-format: 0.2\n'
            '#+name: test-challenge\n'
            '** TEST foo.bar-1 : a fine test\n'
            '#+begin_src\n'
            '> q\n'
            '#+end_src\n'
            '** TEST baz_2.A : another fine test\n'
            '#+begin_src\n'
            '> q\n'
            '#+end_src\n'
        )
        c = self._parse_org(org)
        self.assertEqual(len(c.tests), 2)
        self.assertEqual(c.tests[0].name, 'foo.bar-1')
        self.assertEqual(c.tests[1].name, 'baz_2.A')
