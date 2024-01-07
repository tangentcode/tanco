#!/bin/env python
"""
command-line driver for rogo client.
"""
import sys, cmd, json
from client import RogoClient
import webbrowser


class RogoDriver(cmd.Cmd):
    prompt = ""
    completekey = ''
    cmdqueue = ''

    def __init__(self):
        super().__init__()
        self.client = RogoClient()

    def do_login(self, _arg):
        """Login to the server"""
        pre = self.client.get_pre_token()
        print("pre token: %s" % pre)
        webbrowser.open(self.client.url + '/auth/login?pre=' + pre)
        jwt = self.client.get_jwt(pre=pre)
        print("json web token: %s" % jwt)

    def do_c(self, _arg):
        """List challenges"""
        for x in self.client.list_challenges():
            print(json.dumps([x['name'], x['title']]))

    def do_q(self, _arg):
        """Run the test suite."""
        return True

    def do_EOF(self, _arg):
        """Exit"""
        return True


if __name__ == '__main__':
    d = RogoDriver()
    if len(sys.argv) > 1: d.onecmd(' '.join(sys.argv[1:]))
    else: d.cmdloop()
    sys.stderr.close()
