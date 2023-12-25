import requests


class RogoClient:
    """
    Clent for the Rogo API
    """

    def __init__(self, url='http://127.0.0.1:5000'):
        self.url = url

    def list_challenges(self):
        res = requests.get(self.url + '/c:json')
        return res.json()
