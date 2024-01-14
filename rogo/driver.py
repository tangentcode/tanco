#!/bin/env python
"""
command-line driver for rogo client.
"""
import os, sys, cmd as cmdlib, json, jwt as jwtlib
import sqlite3
import webbrowser

from . import runner, orgtest, database as db
from .client import RogoClient
from .model import Config, TestDescription


class RogoDriver(cmdlib.Cmd):
    prompt = "rogo> "
    completekey = ''
    cmdqueue = ''

    def __init__(self):
        super().__init__()
        self.result = None    # for passing data between commands
        self.client = RogoClient()

    # -- global database state --------------------------------

    def do_login(self, _arg):
        """Login to the server"""
        if who := self.client.whoami():
            print(f"Already logged in to {self.client.url} as {who['username']}.")
            return
        sid = db.get_server_id(self.client.url)
        pre = self.client.get_pre_token()
        webbrowser.open(self.client.url + '/auth/login?pre=' + pre)
        jwt = self.client.get_jwt(pre=pre)
        data = jwtlib.JWT().decode(jwt, do_verify=False)  # TODO: verify

        # TODO: have real usernames
        uid = db.commit(
            'insert into users (sid, authid, username) values (?, ?, ?)',
            [sid, data['uid'], data['eml']])
        db.commit('insert into tokens (uid, jwt) values (?, ?)', [uid, jwt])

    def do_whoami(self, _arg):
        """Show the current user"""
        try:
            who = self.client.whoami()
        except LookupError as e:
            print(e)
            return
        print(f"logged in as {who['username']}" if who else "not logged in.")

    @staticmethod
    def do_delete(arg):
        """Delete a challenge"""
        if not arg:
            print("Usage: `delete <challenge name>`")
            return
        old = db.query('select id from challenges where name=?', [arg])
        if not old:
            print(f'Sorry. Challenge "{arg}" does not exist in the database.')
            return
        old = old[0]['id']
        tx = db.begin()
        tx.execute('delete from tests where chid=?', [old])
        # TODO: tx.execute('delete from progress where chid=?', [old])
        tx.execute('delete from challenges where id=?', [old])
        tx.commit()
        print(f'Challenge "{arg}" deleted.')

    @staticmethod
    def do_import(arg):
        """Import a challenge"""
        if not arg:
            print("usage: import <challenge.org>")
            return
        if os.path.exists(arg):
            c = orgtest.read_challenge(arg)
            if not (sids := db.query('select id from servers where url=?', [c.server])):
                print(f'Sorry, server "{c.server}" is not in the database.')
                return
            sid = sids[0]['id']
            if db.query('select * from challenges where sid=? and name=?', [sid, c.name]):
                print(f'Sorry, challenge "{c.name}" already exists in the database.')
                print(f'Use `rogo delete {c.name}` if you want to replace it.')
                return
            tx = db.begin()
            cur = tx.execute('insert into challenges (sid, name, title) values (?, ?, ?)',
                             [sid, c.name, c.title])
            chid = cur.lastrowid
            for (i, t) in enumerate(c.tests):
                tx.execute("""
                    insert into tests (chid, name, head, body, grp, ilines, olines)
                    values (?, ?, ?, ?, ?, ?, ?)
                    """, [chid, t.name, t.head, t.body, i,
                          '\n'.join(t.ilines), '\n'.join(t.olines)])
            tx.commit()
            print(f'Challenge "{c.name}" imported with {len(c.tests)} tests.')

    def do_challenges(self, _arg):
        """List challenges"""
        print(f'Listing challenges from {self.client.url}')
        print()
        self.result = self.client.list_challenges()
        for c in self.result:
            print(f' {c["name"]:16} : {c["title"]}')
        print()

    # -- local project config ---------------------------------

    def do_init(self, arg):
        """create .rogo file in current directory"""
        if os.path.exists('.rogo'):
            print("Already initialized.")
            return
        if not (who := self.client.whoami()):
            print("Please login first.")
            return

        # either way, the following sets self.result to challenge list
        if arg:
            self.result = self.client.list_challenges()
        else:
            self.do_challenges('')
        while not arg:
            print("Enter the name of the challenge you want to work on.")
            arg = input("> ")
        match = [c for c in self.result if c['name'] == arg]
        if not match:
            print(f"Sorry, challenge '{arg}' not found.")
            return
        c = match[0]
        sid = db.get_server_id(self.client.url)
        chid = db.commit("""insert or replace into challenges
            (sid, name, title) values (?, ?, ?)
            """, [sid, c['name'], c['title']])
        # now we have arg = a valid challenge name on the server,
        # so we have to initialize the attempt on both the remote
        # and local databases.
        aid = self.client.attempt(arg)
        uid = who['id']
        db.commit("""
            insert into attempts (uid, chid, code) values (?, ?, ?)
            """, [uid, chid, aid])
        cfg = Config(attempt=aid)
        with open('.rogo', 'w') as f:
            f.write(cfg.to_json())
        print('Project initialized.')
        print('Edit .rogo to configure how to run your project.')
        print('Then run `rogo check` to make sure rogo can run your program.')

    @staticmethod
    def do_check(arg):
        runner.check(['rogo']+[x for x in arg.split(' ') if x != ''])

    def do_show(self, arg=None):
        """show the current test prompt"""
        cfg = runner.load_config()
        tests = db.get_next_tests(cfg.attempt)
        self.result = (cfg.attempt, tests)
        if tests:
            if arg == '-n':
                print('You already have the next test. Calling `rogo show`:')
                print()
            t = TestDescription(**tests[0])
            print(f'#[{t.name}]: {t.head}')
            print()
            print(t.body)
            print()
            print("Use 'rogo test' to run the tests.")
        elif arg == '-n':
            pass
        else:
            print("No current tests are known.")
            print("Use `rogo next` to fetch the next test.")

    def do_next(self, _arg):
        """fetch the next test"""
        # TODO:  double check that all tests pass and repo is clean

        self.do_show('-n')
        (attempt, known_tests) = self.result
        if known_tests:
            return

        # -- fetch the next test from the server
        tests = self.client.get_next(attempt)
        if not tests:
            print("You have completed the challenge!")
            # TODO: do something when you win
            return
        try:
            chid = db.challenge_from_attempt(attempt).id
            tx = db.begin()
            for t in tests:
                tx.execute("""
                    insert into tests (chid, name, head, body, grp, ord, ilines, olines)
                    values (?, ?, ?, ?, ?, ?, ?, ?)
                    """, [chid, t['name'], t['head'], t['body'], t['grp'], t['ord'],
                          t['ilines'], t['olines']])
            tx.commit()
        except sqlite3.IntegrityError as e:
            # this should not actually happen (because the 'show' call worked)
            # but just in case:
            # print("You've already acquired next tests.")
            print(e)

        self.do_show()


    @staticmethod
    def do_test(arg):
        """Run the tests"""
        runner.main(['rogo']+[x for x in arg.split(' ') if x != ''])

    @staticmethod
    def do_q(_arg):
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
