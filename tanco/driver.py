#!/bin/env python
"""
command-line driver for tanco client.
"""
import argparse
import asyncio
import cmd as cmdlib
import os
import shlex
import sqlite3
import subprocess
import sys
import webbrowser
import pprint

import jwt as jwtlib
import websockets as w

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
        self.target = None    # target program
        self.cmdqueue = ['']
        self.end_cmd = ';'
        self.end_out = ''
        self.output = ''


    # -- global database state --------------------------------

    def do_login(self, _arg):
        """Login to the server"""
        if who := self.client.whoami():
            print(f"Already logged in to {self.client.url} as {who['username']}.")
            return
        sid = db.get_server_id(self.client.url)
        pre = self.client.get_pre_token()
        webbrowser.open(self.client.url + 'auth/login?pre=' + pre)
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

    def do_init(self, arg: str):
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
            print('Enter the name or number of the challenge you want to work on.')
            arg = input('> ')
        if arg.isdigit():
            try:
                arg = self.result[int(arg)]['name']
            except IndexError:
                print(f"Sorry, challenge number {arg} not found.")
                return
        if arg == '--local':
            print('starting local challenge.')
        else:
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

    def do_spawn(self, _arg):
        self.target = runner.spawn(runner.load_config())

    def ensure_target(self):
        if not self.target:
            self.do_spawn('')

    def do_send(self, msg, suppress=False):
        self.ensure_target()
        if msg.endswith(self.end_cmd): msg = msg[:-1]
        self.target.stdin.write(msg + f'\n{self.end_cmd}\n')
        self.target.stdin.flush()
        lines = []
        for line in self.target.stdout:
            line = line.rstrip()
            if line == self.end_out:
                break
            else:
                lines.append(line)
        self.output = '\n'.join(lines)
        if not suppress:
            print(self.output)

    async def ws_talk(self, ws: w.WebSocketCommonProtocol):
        """communicate with a websocket for 'share' and 'bind' commands"""
        self.ensure_target()

        async for msg in ws:
            assert isinstance(msg, str)
            if self.end_cmd in msg:
                await ws.send("WARNING: ';' in message, ignoring")
                continue
            print('RECV:', msg)
            tokens = shlex.split(msg)
            if tokens:
                match tokens[0]:
                    case 'send':
                        cmd = shlex.join(tokens[1:])
                        self.do_send(cmd, suppress=True)
                        res = self.output
                    case 'test':
                        self.do_test('')
                        res = 'ran `tanco test`'
                    case 'next':
                        self.do_next('')
                        res = 'ran `tanco next`'
                    case 'spawn':
                        self.do_spawn('')
                        res = 'ran `tanco spawn`'
                    case _: res = 'ERROR: unknown command'
            else:
                res = 'RECV: ' + msg
            print('res:', res)
            await ws.send(res)

    def do_share(self, _arg):
        """hand control of your working directory over to the tanco server"""
        code = runner.load_config().attempt

        async def share():
            url = self.client.url.replace('http', 'ws', 1) + f'a/{code}/share'
            print(f'connecting to {url}')
            ws = await w.connect(url)
            assert 'hello' == await ws.recv()
            print('connected!')
            await self.ws_talk(ws)

        asyncio.run(share())

    def do_bind(self, arg):
        """serve target program on a given port (default 1234)"""
        port = int(arg) if arg else 1234

        async def bind():
            async with w.serve(self.ws_talk, 'localhost', port):
                print('serving websocket on port', port)
                print('you can talk to it with:')
                print(f'python -m websockets ws://localhost:{port}/')
                await asyncio.Future()

        asyncio.run(bind())

    @staticmethod
    def do_test(arg):
        """Run the tests."""
        runner.main([x for x in arg.split(' ') if x != ''])

    @staticmethod
    def do_q(_arg):
        """Exit the shell."""
        return True

    @staticmethod
    def do_EOF(_arg):
        """Exit when ^D pressed or EOF reached"""
        return True

    def do_run(self, arg):
        """Run tests from an org file or from the database
        Usage: run [-t / --tests ORG_FILE] [-v / --verbose] [PROGRAM_ARGS...]
        """
        parser = argparse.ArgumentParser(prog='run', description='Run tanco tests')
        parser.add_argument('-t', '--tests', help='Path to org file containing tests')
        parser.add_argument('-v', '--verbose', action='store_true', help='Print configuration before running tests')

        # Parse known args first to get tanco args
        try:
            args, program_args = parser.parse_known_args(shlex.split(arg) if arg else [])
        except SystemExit: # Prevent argparse from exiting the Cmd loop
             return

        cfg = runner.load_config()

        # Determine program args and shell usage
        parsed_program_args = []
        explicit_shell = False
        if args.tests:
            cfg.test_path = args.tests
            cfg.attempt = None  # Don't use database when running from org file
            parsed_program_args = program_args # Use remaining args after --tests
        elif program_args:
             # If not --tests, but extra args are given, assume they override .tanco config
             parsed_program_args = program_args
        else:
            # Use args from .tanco or default if no override
            parsed_program_args = cfg.program_args
            explicit_shell = cfg.use_shell # Respect shell setting from .tanco

        # Check for '-c' flag and update cfg for verbose output and potentially runner
        if parsed_program_args and parsed_program_args[0] == '-c':
            cfg.use_shell = True # Set shell=True for verbose output
            # The actual args list passed to spawn still includes '-c' for spawn to process
            cfg.program_args = parsed_program_args
        else:
            cfg.program_args = parsed_program_args
            cfg.use_shell = explicit_shell # Use value from .tanco or default

        # Dump config if verbose flag is set
        if args.verbose:
            print("--- Tanco Configuration ---")
            pprint.pprint(cfg)
            print("---------------------------")

        try:
            # Pass the possibly modified cfg to run_tests
            runner.run_tests(cfg)
        except runner.NoTestPlanError:
            print("No tests specified. Use --tests PATH or ensure you're in a tanco project.")
        except runner.StopTesting:
            pass # Normal exit after test failure
        except Exception:
            # handle_unexpected_error already prints traceback
            runner.handle_unexpected_error(cfg)


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
