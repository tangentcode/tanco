#!/usr/bin/env python
"""
Test-running logic for validating tanco tests.
"""
import errno
import json
import os
import subprocess
import sys
import traceback

from . import database as db
from . import model as m
from . import orgtest
from .client import TancoClient
from .model import Challenge, Config, ResultKind, TestDescription, TestFailure

USER_HELP = """
Tanco can't find your code!

Your first step is to write a *console-mode* program
(one that does absolutely nothing!) and tell tanco
where to find it.

This is configured in your .tanco file, but you can
also use this command to test the configuration before
adding it to that file:

    tanco check [/path/to/your-program] [arguments]

The path should refer to a physical file on disk, so if
you need command line arguments, create a wrapper program.
The default path is "./my-program".

You can pass extra arguments that will be passed to the
target program.

If you need more help with setting up, try reading:
https://github.com/LearnProgramming/learntris/wiki/Getting-Set-Up
(tanco was based on the test runner for learntris)

Once tanco is able to launch your program, this message
will be replaced with instructions for implementing your
first feature.
"""


def load_config() -> Config:
    res = Config()
    res.uid = TancoClient().whoami()['id']
    res.input_path = os.environ.get('INPUT_PATH', '')
    res.skip_lines = int(os.environ.get('SKIP_LINES', '0'))
    res.test_plan = os.environ.get('TEST_PLAN')
    if os.path.exists('.tanco'):
        try:
            data = json.load(open('.tanco'))
            target = data['targets']['main']
        except json.decoder.JSONDecodeError as e:
            print('Error reading .tanco file:', e)
            sys.exit()
        except KeyError:
            print('`targets/main` found in the .tanco file.')
            sys.exit()
        if 'args' not in target:
            print('`targets/main` must specify a list of program arguments.')
            sys.exit()
        res.attempt = data.get('attempt')
        res.program_args = target['args']  # TODO: check that it's actually a list
        res.use_shell = target.get('shell', False)  # TODO: check that it's actually a bool
    return res


class NoTestPlanError(Exception):
    pass


def spawn(program_args, use_shell):
    try:
        return subprocess.Popen(program_args,
                            shell=use_shell,
                            universal_newlines=True,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE)
    except OSError as e:
        if e.errno == errno.ENOENT:
            print("Couldn't find program:", program_args[0])
            print('Make sure you have the right path.')
        else:
            print(f"Couldn't run program '{program_args[0]}':")
            print('  ', e)
        sys.exit()


def send_cmds(cfg: Config, program, ilines):
    if cfg.input_path:
        cmds = open(cfg.input_path, 'w')
        for cmd in ilines:
            cmds.write(cmd + '\n')
        cmds.close()
    else:
        for cmd in ilines:
            program.stdin.write(cmd + '\n')
            program.stdin.flush()


def run_test(cfg: Config, program: subprocess.Popen, test: TestDescription):
    # send all the input lines (to stdin or a file):
    send_cmds(cfg, program, test.ilines)
    # listen for the response:
    (actual, _errs) = program.communicate(timeout=5)
    # TODO: handle errors in the `errs` string
    actual = clean_output(cfg, actual)
    local_check_output(cfg, actual, test)


def clean_output(cfg: Config, actual: str) -> list[str]:
    lines = [line.strip() for line in actual.splitlines()]
    lines = lines[cfg.skip_lines:]
    # strip trailing blank lines
    while lines and lines[-1] == '':
        lines.pop()
    return lines


def save_new_rule(attempt: str, test: str, rule: m.ValidationRule):
    db.save_progress(attempt, test, True)
    db.save_rule(attempt, test, rule.to_data())


def local_check_output(cfg: m.Config, actual: list[str], test: TestDescription):
    local_res = test.check_output(actual)
    match local_res.kind:
        case ResultKind.Pass: pass
        case ResultKind.Fail:
            # a regression! (test failed and have the rule,
            # so we have to tell the server)
            fail(cfg, local_res.error.error_lines(), test.name, local_res)
        case ResultKind.AskServer:
            client = TancoClient()
            remote_res = client.check_output(cfg.attempt, test.name, actual)
            match remote_res.kind:
                case ResultKind.Pass:
                    save_new_rule(cfg.attempt, test.name, remote_res.rule)
                case ResultKind.Fail:
                    raise remote_res.error
                case ResultKind.AskServer:
                    raise RecursionError('Server validation loop')


def get_challenge(cfg: Config) -> Challenge:
    if cfg.test_plan:
        return orgtest.read_challenge(cfg.test_plan)
    elif cfg.attempt:
        return db.challenge_from_attempt(cfg.attempt)
    else:
        raise NoTestPlanError


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
            print('All %d tests passed.' % num_passed)
            print()
            print('This may be a good time to commit your changes,')
            print('or spend some time improving your code.')
            print()
            print("When you're ready, run `tanco next` to start work on the next feature.")
            print()
            TancoClient().send_pass(cfg.attempt)
    except (subprocess.TimeoutExpired, TestFailure) as e:
        print()
        print('%d of %d tests passed.' % (num_passed, len(tests)))
        if isinstance(e, subprocess.TimeoutExpired):
            print('Test [%s] timed out.' % test.name)
        else:
            print('Test [%s] failed.' % test.name)
            print()
            print('#', test.name, test.head)
            print(test.body)
            print(' --- input given ------')
            for line in test.ilines:
                print(line)
            print()
            fail(cfg, e.error_lines(), test)


def find_target(cfg: Config, argv: list[str]) -> Config:
    """returns the config, possibly overridden by command line args"""
    if len(argv) > 1:
        cfg.program_args = argv[1:]
        if '--shell' in cfg.program_args:
            cfg.program_args.remove('--shell')
            cfg.use_shell = True
    if cfg.use_shell or os.path.exists(cfg.program_args[0]):
        return cfg
    elif cfg.program_args[0] == cfg.default_target():
        print(USER_HELP)
    raise FileNotFoundError(cfg.program_args[0])


def get_custom_cfg(argv: list[str]):
    """return a config object, possibly overridden by command line args"""
    cfg = load_config()
    try:
        cfg = find_target(cfg, argv)
    except FileNotFoundError as e:
        print('File not found:', e)
        sys.exit()
    return cfg


TANCO_CHECK = '(tanco check)'


def check(argv: list[str]):
    cfg = get_custom_cfg(argv)
    program = spawn(cfg.program_args, cfg.use_shell)
    test = TestDescription()
    test.name = TANCO_CHECK
    test.head = 'tanco check'
    test.body = '\n'.join([
        'Tanco needs to be able to run your program.',
        'Please make sure that your program is marked as executable,',
        'and that by default, it produces no output and returns exit code 0',
    ])
    try:
        run_test(cfg, program, test)
    except Exception:
        handle_unexpected_error(cfg)
    else:
        print(f"Tanco ran {' '.join(cfg.program_args)} successfully.")
        print('Run `tanco next` to start the first test.')


def fail(cfg: Config, msg: list[str], tn: str | None = None, tr: m.TestResult | None = None):
    if tn == TANCO_CHECK:
        print('`tanco check` failed.')
    for line in msg:
        print(line)
    if tn and tr and (tn != TANCO_CHECK):
        assert tr.kind == ResultKind.Fail, 'Expected a failed test.'
        c = TancoClient()
        c.send_fail(cfg.attempt, tn, tr)
    sys.exit()


def handle_unexpected_error(cfg: Config):
    try:
        fail(cfg, ['-'*50,
                   traceback.format_exc(),
                   '-'*50,
                   'Oh no! Tanco encountered an unexpected problem while',
                   'attempting to run your program. Please report the above',
                   'traceback in the issue tracker, so that we can help you',
                   'with the problem and provide a better error message in',
                   'the future.',
                   '',
                   '  https://github.com/tangentcode/tanco/issues'])
    except Exception as e:
        traceback.print_exception(type(e), e, None)
        sys.exit()


def main(argv: list[str]):
    cfg = get_custom_cfg(argv)
    cmdline = cfg.program_args
    cmd = cmdline[0]
    try:
        run_tests(cfg)
    except NoTestPlanError:
        fail(cfg, ['No challenge selected.'
                   'Use `tanco init` or set TEST_PLAN environment variable.'])
    except EnvironmentError as e:
        if e.errno in [errno.EPERM, errno.EACCES]:
            fail(cfg, [str(e),
                       "Couldn't run %r due to a permission error." % cmd,
                       'Make sure your program is marked as an executable.'])
        elif e.errno == errno.EPIPE:
            fail(cfg, [str(e),
                       '%r quit before reading any input.' % cmd,
                       'Make sure you are reading commands from standard input,',
                       'not trying to take arguments from the command line.'])
        else:
            handle_unexpected_error(cfg)
    except Exception:
        handle_unexpected_error(cfg)


if __name__ == '__main__':
    main(sys.argv)
