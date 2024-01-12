import requests
import os

from . import database as db


class RogoClient:
    """
    Client for the Rogo API
    """

    def __init__(self, url=None):
        self.url = url or os.environ.get('ROGO_SERVER', 'https://rogo.tangentcode.com/')
        if not self.url.endswith('/'):
            self.url += '/'

    def post(self, url, data):
        url = url[1:] if url.startswith('/') else url
        res = requests.post(self.url + url, json=data)
        return res.json()

    def get_pre_token(self):
        return self.post('auth/pre', {})['token']

    def get_jwt(self, pre=None):
        return self.post('auth/jwt', {"pre": pre})['token']

    def list_challenges(self):
        res = requests.get(self.url + 'c:json')
        return res.json()

    def attempt(self, challenge_name):
        who = self.whoami()
        if not who:
            raise LookupError('You must be logged in to attempt a challenge.')
        res = requests.post(self.url + 'c/' + challenge_name + '/attempt', {
            'jwt': who['jwt']})
        return res.json()['aid']

    def whoami(self):
        res = db.query("""
            select u.id, u.username, t.jwt from tokens t, users u, servers s
            where t.uid=u.id and u.sid=s.id and s.url = ?
            """, [self.url])
        if len(res) > 1:
            raise LookupError('Multiple tokens found. This is a server database.')
        return res[0] if res else None
