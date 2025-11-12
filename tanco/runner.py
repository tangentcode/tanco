#!/usr/bin/env python
"""
Test-running logic for validating tanco tests.
"""
import errno
import json
import os
import shutil
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
    kw = {'uid': who['id'] if (who:=TancoClient().whoami()) else None}

    # Load from .tanco file if it exists
    if os.path.exists('.tanco'):
        try:
            data = json.load(open('.tanco'))
            target = data['targets']['main']
        except json.decoder.JSONDecodeError as e:
            print('Error reading .tanco file:', e)
            sys.exit()
        except KeyError:
            print('`targets/main` not found in the .tanco file.') # Corrected error message
            sys.exit()
        if 'args' not in target:
            print('`targets/main` must specify a list of program arguments.')
            sys.exit()
        for slot in Config.__dataclass_fields__.keys():
            if slot in data:
                kw[slot] = data[slot]
        kw['program_args'] = target['args']  # TODO: check that it's actually a list
        kw['use_shell'] = target.get('shell', False)
        # Allow .tanco to override input_path from env
        if 'input_path' in target:
             kw['input_path'] = target['input_path']

    # Load from environment variables (can override .tanco or provide defaults)
    if 'INPUT_PATH' in os.environ and 'input_path' not in kw:
        kw['input_path'] = os.environ['INPUT_PATH']
    if 'TEST_PLAN' in os.environ and 'test_plan' not in kw:
         kw['test_plan'] = os.environ['TEST_PLAN']
    # Add other environment variable checks here if needed

    return Config(**kw)


class NoTestPlanError(Exception):
    pass


class StopTesting(Exception):
    pass


def spawn(cfg: m.Config | None = None):
    if not cfg:
        cfg = load_config()
    program_args, use_shell = cfg.program_args, cfg.use_shell
    cmd_for_popen = None
    prog_name_for_error = "<unknown>" # Default for error messages

    if program_args and program_args[0] == '-c':
        use_shell = True
        cmd_list = program_args[1:]
        if not cmd_list: # Handle case like "tanco run --tests f.org -c"
             fail(cfg, ["Error: '-c' flag used with no command specified."])
        if os.name == 'nt':
            # For Windows shell, join args and replace slashes
            cmd_string = ' '.join(cmd_list)
            cmd_for_popen = cmd_string.replace('/', '\\')
            prog_name_for_error = cmd_for_popen # Use the processed command string for errors
        else:
            # For POSIX with shell=True, must pass a string, not a list
            cmd_for_popen = ' '.join(cmd_list)
            prog_name_for_error = cmd_list[0] # Use the command itself for errors
    else:
        # Not a '-c' command
        cmd_list = list(program_args)
        if not cmd_list:
             fail(cfg, ["Error: No program arguments specified."])
        prog_name_for_error = cmd_list[0]

        # Resolve executables when not using shell (cross-platform)
        if not use_shell:
            # First, try to find the executable in PATH (for things like 'node', 'python', etc.)
            if not os.path.isabs(cmd_list[0]) and not os.path.exists(cmd_list[0]):
                which_result = shutil.which(cmd_list[0])
                if which_result:
                    cmd_list[0] = which_result
                    prog_name_for_error = which_result
                else:
                    # Not in PATH, try as local path
                    if os.name == 'nt':
                        # On Windows, make it absolute for PATHEXT checking below
                        cmd_list[0] = os.path.abspath(cmd_list[0])
                        prog_name_for_error = cmd_list[0]
                    # On POSIX, leave it as-is and let Popen handle it
            elif not os.path.isabs(cmd_list[0]) and os.name == 'nt':
                # Local file exists on Windows, make it absolute
                cmd_list[0] = os.path.abspath(cmd_list[0])
                prog_name_for_error = cmd_list[0]

            # Windows-specific: Check existence with PATHEXT extensions
            if os.name == 'nt' and not os.path.exists(cmd_list[0]):
                found_executable = False
                pathext = os.environ.get('PATHEXT', '.COM;.EXE;.BAT;.CMD').split(';')
                # Ensure extensions start with a dot and handle empty strings
                extensions_to_try = [ext.lower() if ext.startswith('.') else '.' + ext.lower()
                                     for ext in pathext if ext] + [''] # Add empty string to check original

                base_path = cmd_list[0]
                for ext in extensions_to_try:
                    potential_path = base_path + ext
                    if os.path.exists(potential_path):
                        cmd_list[0] = potential_path
                        prog_name_for_error = potential_path
                        found_executable = True
                        break # Found it

                if not found_executable:
                     fail(cfg, [f"Couldn't find program: {base_path} (with extensions)",
                               'Make sure you have the right path and filename.'])

        cmd_for_popen = cmd_list # List for shell=False or POSIX shell=True without -c

    try:
        return subprocess.Popen(cmd_for_popen,
                              shell=use_shell,
                              universal_newlines=True,
                              stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE)
    except OSError as e:
        if e.errno == errno.ENOENT:
            fail(cfg, [str(e),
                      f"Couldn't find program or command: {prog_name_for_error}",
                      'Make sure it is installed and in your PATH or the path is correct.'])
        elif e.errno in [errno.EPERM, errno.EACCES]:
            fail(cfg, [str(e),
                      f"Couldn't run {prog_name_for_error!r} due to a permission error.",
                      'Make sure the file/script has execute permissions.'])
        elif getattr(e, 'winerror', 0) == 193: # Specific check for WinError 193
             fail(cfg, [str(e),
                        f"Command {prog_name_for_error!r} is not a valid executable.",
                        "Make sure you are running scripts via their interpreter (e.g., 'python script.py')",
                        "or using the shell ('-c' flag) if necessary."])
        elif e.errno == errno.EPIPE:
            fail(cfg, [str(e),
                      f'{prog_name_for_error!r} quit before reading any input.',
                      'Make sure it is reading commands from standard input.'])
        else:
            handle_unexpected_error(cfg)


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
            assert local_res.error is not None
            fail(cfg, local_res.error.error_lines(), test, local_res)
        case ResultKind.AskServer:
            if cfg.test_path:  # We're running from org file
                # When running from org file, treat missing output rules as failure
                fail(cfg, ["Test failed - output didn't match expected result"], test)
            else:
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
    if cfg.test_path:
        return orgtest.read_challenge(cfg.test_path)
    elif cfg.test_plan:
        return orgtest.read_challenge(cfg.test_plan)
    elif cfg.attempt:
        return db.challenge_from_attempt(cfg.attempt)
    else:
        raise NoTestPlanError("No tests specified. Use --tests PATH or ensure you're in a tanco project.")


def run_tests(cfg: Config, names=None):
    num_passed = 0
    challenge = get_challenge(cfg)
    tests = challenge.tests
    try:
        for i, test in enumerate(tests):
            if names and test.name not in names: continue
            program = spawn(cfg)
            run_test(cfg, program, test)
            # either it passed or threw exception
            print('.', end='', flush=True)
            num_passed += 1
        else:
            print()
            print('All %d tests passed.' % num_passed)
            print()
            if cfg.test_path:
                print('All tests in %s passed.' % cfg.test_path)
            else:
                print('This may be a good time to commit your changes,')
                print('or spend some time improving your code.')
                if cfg.attempt:
                    print()
                    print("When you're ready, run `tanco next` to start work on the next feature.")
                    print()
                    TancoClient().send_pass(cfg)
    except (subprocess.TimeoutExpired, TestFailure) as e:
        # TODO: is this even reachable??
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
    program = spawn(cfg)
    test = TestDescription()
    test.name = TANCO_CHECK
    test.head = 'tanco check'
    test.body = '\n'.join([
        'Tanco needs to be able to run your program.',
        'Please make sure that your program is marked as executable,',
        'and that by default, it produces no output and returns exit code 0'])
    try:
        run_test(cfg, program, test)
    except Exception:
        handle_unexpected_error(cfg)
    else:
        print(f"Tanco ran {' '.join(cfg.program_args)} successfully.")
        print('Run `tanco next` to start the first test.')


def error(cfg: Config, msg: list[str]):
    fail(cfg, msg)


def fail(cfg: Config, lines: list[str], test: m.TestDescription | None = None, tr: m.TestResult | None = None):
    print("\n")
    if test and test.name == TANCO_CHECK:
        print('`tanco check` failed.')
    elif test:
        print('Test [%s] failed.' % test.name)
        if test.head:
            print('###', test.head)
        if test.body:
            print(test.body)
        print()
        print(' --- input given ------')
        for line in test.ilines:
            print(line)
        print()
    # Always print the specific error lines
    for line in lines:
        print(line)

    # Server interaction logic (only if not in local --tests mode)
    if not cfg.test_path:
        if test and test.name and tr and (test.name != TANCO_CHECK):
            assert tr.kind == ResultKind.Fail, 'Expected a failed test result object.'
            try:
                c = TancoClient()
                c.send_fail(cfg, test.name, tr)
            except Exception as client_e:
                print(f"\nError reporting failure to server: {client_e}")

    # Stop testing after failure
    raise StopTesting() # Raise consistently


def handle_unexpected_error(cfg: Config):
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


def main(names: list[str]):
    cfg = load_config()
    try:
        run_tests(cfg, names)
    except NoTestPlanError:
        error(cfg, ['No challenge selected.'
                    'Use `tanco init` or set TEST_PLAN environment variable.'])
    except StopTesting:
        pass
    except Exception:
        handle_unexpected_error(cfg)


if __name__ == '__main__':
    main(sys.argv)
