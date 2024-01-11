#!/bin/env python
"""
command-line driver for rogo client.
"""
import os, sys, cmd as cmdlib, json
import webbrowser

from . import runner, orgtest, database as db
from .client import RogoClient


class RogoDriver(cmdlib.Cmd):
    prompt = "rogo> "
    completekey = ''
    cmdqueue = ''

    def __init__(self):
        super().__init__()
        self.client = RogoClient()

    # -- global database state --------------------------------

    def do_login(self, _arg):
        """Login to the server"""
        pre = self.client.get_pre_token()
        print("pre token: %s" % pre)
        webbrowser.open(self.client.url + '/auth/login?pre=' + pre)
        jwt = self.client.get_jwt(pre=pre)
        print("json web token: %s" % jwt)

    def do_delete(self, arg):
        """Delete a challenge"""
        if not arg:
            print("Usage: `delete <challenge name>`")
            return
        old = db.query('select rowid as id from challenges where name=?', [arg])
        if not old:
            print(f'Sorry. Challenge "{arg}" does not exist in the database.')
            return
        old = old[0]['id']
        tx = db.begin()
        tx.execute('delete from tests where chid=?', [old])
        # TODO: tx.execute('delete from progress where chid=?', [old])
        tx.execute('delete from challenges where rowid=?', [old])
        tx.commit()
        print(f'Challenge "{arg}" deleted.')

    def do_import(self, arg):
        """Import a challenge"""
        if not arg:
            print("usage: import <challenge.org>")
            return
        if os.path.exists(arg):
            c = orgtest.read_challenge(arg)
            if db.query('select * from challenges where name=?', [c.name]):
                print(f'Sorry, challenge "{c.name}" already exists in the database.')
                print(f'Use `rogo delete {c.name}` if you want to replace it.')
                return
            tx = db.begin()
            cur = tx.execute('insert into challenges (name, title, url) values (?, ?, ?)',
                             [c.name, c.title, c.url])
            chid = cur.lastrowid
            for t in c.tests:
                tx.execute('insert into tests (chid, name, head, body, ilines, olines) values (?, ?, ?, ?, ?, ?)',
                           [chid, t.name, t.head, t.body, '\n'.join(t.ilines), '\n'.join(t.olines)])
            tx.commit()
            print(f'Challenge "{c.name}" imported with {len(c.tests)} tests.')

    def do_challenges(self, _arg):
        """List challenges"""
        for x in self.client.list_challenges():
            print(json.dumps([x['name'], x['title']]))

    # -- local project config ---------------------------------

    def do_init(self, arg):
        print('TODO: rogo init')
        print('For now, please copy the main .rogo file from github:')
        print('  https://raw.githubusercontent.com/tangentstorm/rogo/main/.rogo')
        print('and modify it yourself.')

    def do_test(self, arg):
        """Run the tests"""
        runner.main(['rogo']+[x for x in arg.split(' ') if x != ''])


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


def main():
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


if __name__ == '__main__':
    main()
