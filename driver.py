#!/bin/env python
"""
command-line driver for rogo client.
"""
import os, sys, cmd as cmdlib, json
import webbrowser

import runner
import orgtest
from client import RogoClient


class RogoDriver(cmdlib.Cmd):
    prompt = "rogo> "
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

    def do_import(self, arg):
        """Import a challenge"""
        if not arg:
            print("usage: import <challenge.org>")
            return
        if os.path.exists(arg):
            tests = orgtest.tests(arg)
            for t in tests:
                print(t.name)

    def do_test(self, args):
        """Run the tests"""
        runner.main(['rogo']+[x for x in args.split(' ') if x != ''])

    def do_challenges(self, _arg):
        """List challenges"""
        for x in self.client.list_challenges():
            print(json.dumps([x['name'], x['title']]))

    def do_q(self, _arg):
        """Exit the shell"""
        return True

    def do_EOF(self, _arg):
        """Exit when ^D pressed or EOF reached"""
        return True


def show_help():
    print("rogo command line client")
    print()
    print("usage: rogo [command]")
    print()
    print("available commands:")
    print()
    data = [(meth[3:], getattr(RogoDriver, meth).__doc__)
            for meth in dir(RogoDriver)
            if meth.startswith('do_')]
    data.append(['shell', 'Run an interactive shell'])
    for cmd, doc in data:
        if cmd in ('EOF', 'help', 'q'): continue
        print("  %-16s:  %s" % (cmd, doc))


if __name__ == '__main__':
    d = RogoDriver()
    if "-q" in sys.argv:
        sys.argv.remove('-q')
        d.prompt = ""
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'shell': d.cmdloop()
        else: d.onecmd(' '.join(sys.argv[1:]))
    else: show_help()
    sys.stderr.close()   # suppress warning on timeout when self-testing
