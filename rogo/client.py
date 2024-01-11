import requests
import os


class RogoClient:
    """
    Client for the Rogo API
    """

    def __init__(self, url=None):
        self.url = url or os.environ.get('ROGO_SERVER', 'https://rogo.tangentcode.com')

    def post(self, url, data):
        url = url if url.startswith('/') else '/' + url
        res = requests.post(self.url + url, json=data)
        return res.json()

    def get_pre_token(self):
        return self.post('auth/pre', {})['token']

    def get_jwt(self, pre=None):
        return self.post('auth/jwt', {"pre": pre})['token']

    def list_challenges(self):
        res = requests.get(self.url + '/c:json')
        return res.json()
