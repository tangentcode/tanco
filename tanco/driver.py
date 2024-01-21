#!/bin/env python
"""
command-line driver for tanco client.
"""
import cmd as cmdlib
import os
import sqlite3
import subprocess
import sys
import webbrowser

import jwt as jwtlib

from . import database as db
from . import model as m
from . import orgtest, runner
from .client import TancoClient
from .model import Config, TestDescription

class TancoDriver(cmdlib.Cmd):
    prompt = 'tanco> '
    completekey = ''

    def __init__(self):
        super().__init__()
        self.result = None    # for passing data between commands
        self.client = TancoClient()
        self.cmdqueue = ['']

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
        uid = db.uid_from_tokendata(sid, data['authid'], data['username'])
        db.commit('insert into tokens (uid, jwt) values (?, ?)', [uid, jwt])

    def do_whoami(self, _arg):
        """Show the current user"""
        try:
            who = self.client.whoami()
        except LookupError as e:
            print(e)
            return
        print(f"logged in as {who['username']}" if who else 'not logged in.')

    @staticmethod
    def do_delete(arg):
        """Delete a challenge"""
        if not arg:
            print('Usage: `delete <challenge name>`')
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
            print('usage: import <challenge.org>')
            return
        if os.path.exists(arg):
            c = orgtest.read_challenge(arg)
            if not (sids := db.query('select id from servers where url=?', [c.server])):
                print(f'Sorry, server "{c.server}" is not in the database.')
                return
            sid = sids[0]['id']
            if db.query('select * from challenges where sid=? and name=?', [sid, c.name]):
                print(f'Sorry, challenge "{c.name}" already exists in the database.')
                print(f'Use `tanco delete {c.name}` if you want to replace it.')
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
        """Create .tanco file in current directory"""
        if not (who := self.client.whoami()):
            print('Please login first.')
            return

        if os.path.exists('.tanco'):
            cfg = runner.load_config()
            if cfg.attempt:
                print('Already initialized.')
                print("Remove the 'attempt' field from .tanco if you")
                print('really want to run `tanco init` again.')
                return
        else:
            cfg = Config()

        if arg:
            self.result = self.client.list_challenges()
        else:
            self.do_challenges('')
        while not arg:
            print('Enter the name of the challenge you want to work on.')
            arg = input('> ')
        match = [c for c in self.result if c['name'] == arg]
        if not match:
            print(f"Sorry, challenge '{arg}' not found.")
            return
        c = match[0]
        sid = db.get_server_id(self.client.url)
        db.commit("""insert or ignore into challenges
            (sid, name, title) values (?, ?, ?)
            """, [sid, c['name'], c['title']])
        chid = db.query('select id from challenges where name=?', [c['name']])[0]['id']
        # now we have arg = a valid challenge name on the server,
        # so we have to initialize the attempt on both the remote
        # and local databases.
        code = self.client.attempt(arg)
        uid = who['id']
        db.commit("""
            insert into attempts (uid, chid, code) values (?, ?, ?)
            """, [uid, chid, code])
        cfg.attempt = code
        with open('.tanco', 'w') as f:
            f.write(cfg.to_json())
        print('Project initialized.')
        print('Edit .tanco to configure how to run your project.')
        print('Then run `tanco check` to make sure tanco can run your program.')

    @staticmethod
    def do_check(arg):
        """Check that the target program runs."""
        runner.check(['tanco']+[x for x in arg.split(' ') if x != ''])

    def do_show(self, arg=None):
        """Show a description of the current test."""
        cfg = runner.load_config()
        state = db.current_state(cfg.attempt)
        if state == 'start':
            print('You have not started the challenge yet.')
            print('Use `tanco check` to make sure your program runs.')
            print('Use `tanco next` to fetch the first test.')
            return
        tests = db.get_next_tests(cfg.attempt, cfg.uid)
        self.result = (cfg.attempt, tests)
        if tests:
            if arg == '-n':
                print('You already have the next test. Calling `tanco show`:')
                print()
            t = TestDescription(**tests[0])
            print(f'#[{t.name}]: {t.head}')
            print()
            print(t.body)
            print()
            print("Use 'tanco test' to run the tests.")
        elif arg == '-n':
            pass
        else:
            print('All known tests have passed.')
            print('Use `tanco test` to check that they still pass.')
            print('Use `tanco next` to fetch the next test.')

    @staticmethod
    def do_version(_arg):
        """Print tanco version (by calling `pip show tanco`) """
        subprocess.run(['pip', 'show', 'tanco'])

    @staticmethod
    def do_status(_arg):
        """print information about the current attempt"""
        cfg = runner.load_config()
        if not cfg.attempt:
            print('No attempt in progress.')
            print('Use `tanco init` to start a new attempt.')
            return
        try:
            s = db.current_status(cfg.attempt)
            print('server:', s['server'])
            print('attempt:', cfg.attempt)
            print('challenge:', s['challenge'])
            print(f"state: {s['state']} {s['focus'] or ''}")
        except LookupError:
            print('attempt: ', cfg.attempt)
            print('attempt (or corresponding challenge) not found in database.')
            print('consider running `tanco recover`')

    def do_next(self, _arg):
        """Fetch the next test from the server."""
        # TODO:  double check that all tests pass and repo is clean

        cfg = runner.load_config()
        state = db.current_state(cfg.attempt)
        if state == 'done':
            print('You have already completed the challenge!')
            return
        elif state != 'start':
            # use `tanco show` to see if we already have the next test:
            self.do_show('-n')
            (attempt, known_tests) = self.result
            if known_tests:
                return

        # -- fetch the next test from the server
        tests = self.client.get_next(cfg.attempt)
        if not tests:
            print('You have completed the challenge!')
            db.set_attempt_state(cfg.uid, cfg.attempt, m.Transition.Done)
            # TODO: do something when you win
            return
        try:
            chid = db.challenge_from_attempt(cfg.attempt).id
            tx = db.begin()
            for t in tests:
                tx.execute("""
                    insert into tests (chid, name, head, body, grp, ord, ilines, olines)
                    values (?, ?, ?, ?, ?, ?, ?, ?)
                    """, [chid, t['name'], t['head'], t['body'], t['grp'], t['ord'],
                          t['ilines'], t['olines']])
            tx.commit()
            # have to do this second, or it'll transition to 'done'!!
            db.set_attempt_state(cfg.uid, cfg.attempt, m.Transition.Next)
        except sqlite3.IntegrityError as e:
            # this should not actually happen (because the 'show' call worked)
            # but just in case:
            print(e)

        self.do_show()

    @staticmethod
    def do_test(arg):
        """Run the tests."""
        runner.main(['tanco']+[x for x in arg.split(' ') if x != ''])

    @staticmethod
    def do_q(_arg):
        """Exit the shell."""
        return True

    @staticmethod
    def do_EOF(_arg):
        """Exit when ^D pressed or EOF reached"""
        return True


def show_help():
    print('tanco command line client')
    print()
    print('usage: tanco [command]')
    print()
    print('available commands:')
    print()
    data = [(meth[3:], getattr(TancoDriver, meth).__doc__)
            for meth in dir(TancoDriver)
            if meth.startswith('do_')]
    data.append(['shell', 'Run an interactive shell'])
    for cmd, doc in data:
        if cmd in ('EOF', 'help', 'q'): continue
        print('  %-16s:  %s' % (cmd, doc))


def main():
    db.ensure_sdb()
    d = TancoDriver()
    if '-q' in sys.argv:
        sys.argv.remove('-q')
        d.prompt = ''
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'shell': d.cmdloop()
        else: d.onecmd(' '.join(sys.argv[1:]))
    else: show_help()
    sys.stderr.close()   # suppress warning on timeout when self-testing


if __name__ == '__main__':
    main()
