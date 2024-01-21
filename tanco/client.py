import os

import requests

from . import database as db
from . import model as m

class TancoClient:
    """
    Client for the Tanco API
    """

    def __init__(self, url=None):
        self.url = url or os.environ.get('TANCO_SERVER', 'https://tanco.tangentcode.com/')
        if not self.url.endswith('/'):
            self.url += '/'

    def post(self, url, data):
        url = url[1:] if url.startswith('/') else url
        res = requests.post(self.url + url, json=data)
        return res.json()

    def get_pre_token(self):
        return self.post('auth/pre', {})['token']

    def get_jwt(self, pre=None):
        return self.post('auth/jwt', {'pre': pre})['token']

    def list_challenges(self):
        res = requests.get(self.url + 'c.json')
        return res.json()

    def attempt(self, challenge_name):
        who = self.whoami()
        if not who:
            raise LookupError('You must be logged in to attempt a challenge.')
        res = requests.post(self.url + 'c/' + challenge_name + '/attempt',
                            json={'jwt': who['jwt']})
        return res.json()['aid']

    def whoami(self):
        res = db.query("""
            select u.id, u.username, t.jwt from tokens t, users u, servers s
            where t.uid=u.id and u.sid=s.id and s.url = ?
            """, [self.url])
        if len(res) > 1:
            raise LookupError('Multiple tokens found. This is a server database.')
        return res[0] if res else None

    def get_next(self, attempt):
        who = self.whoami()
        if not who:
            raise LookupError('You must be logged in to get next test.')
        return self.post('a/' + attempt + '/next', {'jwt': who['jwt']})

    def send_pass(self, attempt):
        who = self.whoami()
        if not who:
            raise LookupError('You must be logged in to send result.')
        db.set_attempt_state(who['id'], attempt, m.Transition.Pass)
        return self.post('a/' + attempt + '/pass', {
            'jwt': who['jwt']})

    def send_fail(self, attempt, test_name: str, result: m.TestResult):
        who = self.whoami()
        if not who:
            raise LookupError('You must be logged in to send result.')
        db.set_attempt_state(who['id'], attempt, m.Transition.Fail, test_name)
        return self.post('a/' + attempt + '/fail', {
            'jwt': who['jwt'],
            'test_name': test_name,
            'result': result.to_data()})

    def check_output(self, attempt: str, test_name: str, actual: list[str]):
        who = self.whoami()
        if not who:
            raise LookupError('You must be logged in to check output.')
        res = self.post(f'a/{attempt}/check/{test_name}', {
            'jwt': who['jwt'],
            'actual': actual})
        return m.TestResult.from_data(res)
