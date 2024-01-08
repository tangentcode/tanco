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
import orgtest
from test_desc import TestDescription

# where to write the input to the child program
# (for cases where stdin is not available)
INPUT_PATH = os.environ.get("INPUT_PATH", "")

# skip this many lines of input before sending
# for cases where the language prints a header
# that can't be suppressed. (e.g. Godot4 - you can turn
# off the header, but doing so turns off all prints!)
SKIP_LINES = int(os.environ.get("SKIP_LINES", "0"))

TEST_PLAN = os.environ.get("TEST_PLAN", "testplan.org")

if sys.version_info.major < 3:
    print("Sorry, rogo requires Python 3.x.")
    sys.exit(1)


class TestFailure(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


def spawn(program_args, use_shell):
    return subprocess.Popen(program_args,
                            shell=use_shell,
                            universal_newlines=True,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE)


def send_cmds(program, ilines):
    if INPUT_PATH:
        cmds = open(INPUT_PATH, "w")
        for cmd in ilines:
            cmds.write(cmd + "\n")
        cmds.close()
    else:
        for cmd in ilines:
            program.stdin.write(cmd + "\n")
            program.stdin.flush()
        program.stdin.close()


def run_test(program: subprocess.Popen, test: TestDescription):
    # send all the input lines (to stdin or a file):
    send_cmds(program, test.ilines)
    # listen for the response:
    (actual, _errs) = program.communicate(timeout=5)
    # TODO: handle errors in the `errs` string
    actual = [line.strip() for line in actual.splitlines()]
    actual = actual[SKIP_LINES:]
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


def run_tests(program_args, use_shell):
    num_passed = 0
    tests = orgtest.tests(TEST_PLAN)
    try:
        for i, test in enumerate(tests):
            program = spawn(program_args, use_shell)
            run_test(program, test)
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


def find_target():
    """returns (program_args, use_shell)"""
    default = "./my-program"
    use_shell = False
    if len(sys.argv) > 1:
        program_args = sys.argv[1:]
        if "--shell" in program_args:
            program_args.remove("--shell")
            use_shell = True
    elif os.path.exists('.rogo'):
        try:
            data = json.load(open('.rogo'))['targets']['main']
        except json.decoder.JSONDecodeError as e:
            print("Error reading .rogo file:", e)
            sys.exit()
        except KeyError:
            print("`targets/main` found in the .rogo file.")
            sys.exit()
        if 'args' not in data:
            print("`targets/main` must specify a list of program arguments.")
            sys.exit()
        program_args = data['args']  # TODO: check that it's actually a list
        use_shell = data.get('shell', False)  # TODO: check that it's actually a bool
    else:
        program_args = [default]

    if use_shell:
        return program_args, True
    elif os.path.exists(program_args[0]):
        return program_args, False
    elif program_args[0] == default:
        print(__doc__)
        raise FileNotFoundError(default)
    else:
        raise FileNotFoundError("%s" % program_args[0])


def main():
    try:
        cmdline, use_shell = find_target()
    except FileNotFoundError as e:
        print('File not found:', e)
    else:
        cmd = cmdline[0]
        try:
            try:
                run_tests(cmdline, use_shell)
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
    main()
