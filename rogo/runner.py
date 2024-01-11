#!/usr/bin/env python
"""
If you're seeing this message when you tried to run
rogo.py, it means rogo can't find your code!

Your first step is to write a *console-mode* program
(one that does absolutely nothing!) and tell rogo
where to find it.

This is configured in your .rogo file, but you can also do this:

    ./rogo.py [/path/to/your-program] [arguments]

The path should refer to a physical file on disk, so if
you need command line arguments, create a wrapper program.
The default path is "./my-program".

You can pass extra arguments that will be passed to the
target program.

If you need more help with setting up, try reading:
https://github.com/LearnProgramming/learntris/wiki/Getting-Set-Up
(rogo was based on the test runner for learntris)

Once rogo is able to launch your program, this message
will be replaced with instructions for implementing your
first feature.
"""
import sys, os, errno, subprocess, difflib, traceback, json

from . import orgtest, database as db
from .model import TestDescription, Config, Challenge


def load_config() -> Config:
    res = Config()
    res.input_path = os.environ.get("INPUT_PATH", "")
    res.skip_lines = int(os.environ.get("SKIP_LINES", "0"))
    res.test_plan = os.environ.get("TEST_PLAN")
    if os.path.exists('.rogo'):
        try:
            data = json.load(open('.rogo'))
            target = data['targets']['main']
        except json.decoder.JSONDecodeError as e:
            print("Error reading .rogo file:", e)
            sys.exit()
        except KeyError:
            print("`targets/main` found in the .rogo file.")
            sys.exit()
        if 'args' not in target:
            print("`targets/main` must specify a list of program arguments.")
            sys.exit()
        res.challenge_url = data['challenge_url']
        res.program_args = target['args']  # TODO: check that it's actually a list
        res.use_shell = target.get('shell', False)  # TODO: check that it's actually a bool
    return res


class TestFailure(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


class NoTestPlanError(Exception):
    pass


def spawn(program_args, use_shell):
    return subprocess.Popen(program_args,
                            shell=use_shell,
                            universal_newlines=True,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE)


def send_cmds(cfg: Config, program, ilines):
    if cfg.input_path:
        cmds = open(cfg.input_path, "w")
        for cmd in ilines:
            cmds.write(cmd + "\n")
        cmds.close()
    else:
        for cmd in ilines:
            program.stdin.write(cmd + "\n")
            program.stdin.flush()
        program.stdin.close()


def run_test(cfg: Config, program: subprocess.Popen, test: TestDescription):
    # send all the input lines (to stdin or a file):
    send_cmds(cfg, program, test.ilines)
    # listen for the response:
    (actual, _errs) = program.communicate(timeout=5)
    # TODO: handle errors in the `errs` string
    actual = [line.strip() for line in actual.splitlines()]
    actual = actual[cfg.skip_lines:]
    # strip trailing blank lines
    while actual and actual[-1] == "":
        actual.pop()
    if actual != test.olines:
        print()
        print("test [%s] failed" % test.head)
        print("---- input ----")
        for cmd in test.ilines:
            print(cmd)
        print(test.body)
        # print("---- expected results ----")
        # print('\n'.join(opcodes['out']))
        print("---- diff of expected vs actual ----")
        diff = '\n'.join(list(difflib.Differ().compare(actual, test.olines)))
        print(diff)
        raise TestFailure('output mismatch')


def get_challenge(cfg: Config) -> Challenge:
    if cfg.test_plan:
        return orgtest.read_challenge(cfg.test_plan)
    elif cfg.challenge_url:
        return db.fetch_challenge(cfg.challenge_url)
    else:
        raise NoTestPlanError()


def run_tests(cfg: Config):
    num_passed = 0
    challenge = get_challenge(cfg)
    tests = challenge.tests
    try:
        for i, test in enumerate(tests):
            program = spawn(cfg.program_args, cfg.use_shell)
            run_test(cfg, program, test)
            # either it passed or threw exception
            print('.', end='')
            num_passed += 1
        else:
            print()
            print("All %d tests passed." % num_passed)
    except (subprocess.TimeoutExpired, TestFailure) as e:
        print()
        print("%d of %d tests passed." % (num_passed, len(tests)))
        if isinstance(e, subprocess.TimeoutExpired):
            print("Test [%s] timed out." % test.name)
        else:
            print("Test [%s] failed." % test.name)


def find_target(cfg: Config, argv: [str]) -> Config:
    """returns the config, possibly overridden by command line args"""
    if len(argv) > 1:
        cfg.program_args = argv[1:]
        if "--shell" in cfg.program_args:
            cfg.program_args.remove("--shell")
            cfg.use_shell = True
    if cfg.use_shell or os.path.exists(cfg.program_args[0]):
        return cfg
    elif cfg.program_args[0] == cfg.default_target():
        print(__doc__)
    raise FileNotFoundError(cfg.program_args[0])


def main(argv: [str]):
    cfg = load_config()
    try:
        cfg = find_target(cfg, argv)
    except FileNotFoundError as e:
        print('File not found:', e)
    else:
        cmdline = cfg.program_args
        cmd = cmdline[0]
        try:
            try:
                run_tests(cfg)
            except NoTestPlanError as e:
                print('No challenge selected.')
                print('Use `rogo init` or set TEST_PLAN environment variable.')
            except EnvironmentError as e:
                if e.errno in [errno.EPERM, errno.EACCES]:
                    print(); print(e)
                    print("Couldn't run %r due to a permission error." % cmd)
                    print("Make sure your program is marked as an executable.")
                elif e.errno == errno.EPIPE:
                    print(); print(e)
                    print("%r quit before reading any input." % cmd)
                    print("Make sure you are reading commands from standard input,")
                    print("not trying to take arguments from the command line.")
                else:
                    raise
        except:
            print('-'*50)
            traceback.print_exc()
            print('-'*50)
            print("Oh no! Rogo encountered an unexpected problem while")
            print("attempting to run your program. Please report the above")
            print("traceback in the issue tracker, so that we can help you")
            print("with the problem and provide a better error message in")
            print("the future.")
            print()
            print("  https://github.com/tangentstorm/rogo/issues")
            print()


if __name__ == '__main__':
    main(sys.argv)
