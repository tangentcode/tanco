#!/usr/bin/env python
"""
Test-running logic for validating rogo tests.
"""
import sys, os, errno, subprocess, traceback, json

from . import orgtest, database as db
from . import model as m
from .model import TestDescription, Config, Challenge, ResultKind, TestFailure
from .client import RogoClient

USER_HELP = """
Rogo can't find your code!

Your first step is to write a *console-mode* program
(one that does absolutely nothing!) and tell rogo
where to find it.

This is configured in your .rogo file, but you can
also use this command to test the configuration before
adding it to that file:

    rogo check [/path/to/your-program] [arguments]

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
            print("Make sure you have the right path.")
        else:
            print(f"Couldn't run program '{program_args[0]}':")
            print('  ', e)
        sys.exit()


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
    actual = clean_output(cfg, actual)
    local_check_output(cfg, actual, test)


def clean_output(cfg: Config, actual: [str]) -> [str]:
    actual = [line.strip() for line in actual.splitlines()]
    actual = actual[cfg.skip_lines:]
    # strip trailing blank lines
    while actual and actual[-1] == "":
        actual.pop()
    return actual


def save_new_rule(attempt: str, test: str, rule: m.ValidationRule):
    db.save_progress(attempt, test, True)
    db.save_rule(attempt, test, rule.to_data())


def local_check_output(cfg: m.Config, actual: [str], test: TestDescription):
    local_res = test.check_output(actual)
    match local_res.kind:
        case ResultKind.Pass: pass
        case ResultKind.Fail: raise local_res.error
        case ResultKind.AskServer:
            client = RogoClient()
            remote_res = client.check_output(cfg.attempt, test.name, actual)
            match remote_res.kind:
                case ResultKind.Pass:
                    save_new_rule(cfg.attempt, test.name, remote_res.rule)
                case ResultKind.Fail:
                    raise remote_res.error
                case ResultKind.AskServer:
                    raise RecursionError("Server validation loop")


def get_challenge(cfg: Config) -> Challenge:
    if cfg.test_plan:
        return orgtest.read_challenge(cfg.test_plan)
    elif cfg.attempt:
        return db.challenge_from_attempt(cfg.attempt)
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
            print()
            print("This may be a good time to commit your changes,")
            print("or spend some time improving your code.")
            print()
            print("When you're ready, run `rogo next` to start work on the next feature.")
            print()
    except (subprocess.TimeoutExpired, TestFailure) as e:
        print()
        print("%d of %d tests passed." % (num_passed, len(tests)))
        if isinstance(e, subprocess.TimeoutExpired):
            print("Test [%s] timed out." % test.name)
        else:
            print("Test [%s] failed." % test.name)
            print()
            print('#', test.name, test.head)
            print(test.body)
            print(" --- input given ------")
            for line in test.ilines:
                print(line)
            print()
            e.print_error()


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
        print(USER_HELP)
    raise FileNotFoundError(cfg.program_args[0])


def get_custom_cfg(argv: [str]):
    """return a config object, possibly overridden by command line args"""
    cfg = load_config()
    try:
        cfg = find_target(cfg, argv)
    except FileNotFoundError as e:
        print('File not found:', e)
        sys.exit()
    return cfg


def handle_unexpected_error():
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


def check(argv: [str]):
    cfg = get_custom_cfg(argv)
    program = spawn(cfg.program_args, cfg.use_shell)
    test = TestDescription()
    test.name = 'check'
    test.head = 'rogo check'
    test.body = '\n'.join([
        "Rogo needs to be able to run your program.",
        "Please make sure that your program is marked as executable,",
        "and that by default, it produces no output and returns exit code 0"
    ])
    try:
        run_test(cfg, program, test)
    except:
        handle_unexpected_error()
    else:
        print(f"Rogo ran {' '.join(cfg.program_args)} successfully.")
        print("Run `rogo next` to start the first test.")


def main(argv: [str]):
    cfg = get_custom_cfg(argv)
    cmdline = cfg.program_args
    cmd = cmdline[0]
    try:
        run_tests(cfg)
    except NoTestPlanError as e:
        print('No challenge selected.')
        print('Use `rogo init` or set TEST_PLAN environment variable.')
    except EnvironmentError as e:
        if e.errno in [errno.EPERM, errno.EACCES]:
            print(e)
            print("Couldn't run %r due to a permission error." % cmd)
            print("Make sure your program is marked as an executable.")
        elif e.errno == errno.EPIPE:
            print(); print(e)
            print("%r quit before reading any input." % cmd)
            print("Make sure you are reading commands from standard input,")
            print("not trying to take arguments from the command line.")
        else:
            handle_unexpected_error()
    except:
        handle_unexpected_error()


if __name__ == '__main__':
    main(sys.argv)
