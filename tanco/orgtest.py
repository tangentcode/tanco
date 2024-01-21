"""
Implements a finite state machine to extract tanco
test descriptions from org files.

The org file format is described here:

  http://orgmode.org/worg/dev/org-syntax.html

However, there is no need to fully parse the outline
structure, since we are only interested in the actual
test cases, and these are clearly marked off by lines
in the following format:

   #+name: testname
   #+begin_src
    <test code winds up here>
   #+end_src

Test lines are simple sequences of lines in the
following format:

- Lines that begin with ">" are input lines.
  The test runner will send these to your program.

- Lines that begin with "'" are test descriptions,
  explaining the purpose of the test to the user.

- The "#" character indicates a comment, which is
  shown to the user but not part of the expected
  output.

- The "\" character can be used to escape any of
  these special characters (including itself).

"""
import os
from collections import namedtuple

from .model import Challenge, TestDescription

OldTestDescription = namedtuple('TestDescription', ['name', 'lines'])


class TestReaderStateMachine:
    """
    A simple finite state machine to extract tests from an outline.
    """
    def __init__(self):
        self.states = [ # NOTE: this is ordered and first field should == index
            (0, self.do_nothing),
            (1, self.on_test_code),
            (2, self.on_meta_line)]  # initial state for reading meta-data
        self.transitions = [
            (0, '#+name:', 0, self.on_test_name),
            (0, '#+begin_src', 1, self.on_begin_test),
            (1, '#+end_src',   0, self.on_end_test)]
        self.state = 2
        self.lineno = 0
        self.next_name = self.prev_name = ''
        self.test_names = []  # only for unique names
        self.tests = []       # collected (name, lines) descriptions
        self.challenge = Challenge()
        self.focus = None     # used to collect lines for current test

    # -- event handlers -----------------------------------------

    def on_line(self, line):
        self.lineno += 1
        match = [row[2:] for row in self.transitions 
                 if row[0] == self.state and line.startswith(row[1])]
        if match:  # match :: [( to_state, method )] of len 1
            self.state = match[0][0]
            match[0][1](line)
        else: self.states[self.state][1](line)

    def do_nothing(self, line):
        pass

    def on_meta_line(self, line):
        c = self.challenge
        if line.startswith('#+title:'):
            c.title = line.split(':')[1].strip()
        elif line.startswith('#+server:'):
            c.server = line.split(' ', 1)[1].strip()
        elif line.startswith('#+name:'):
            c.name = line.split(' ', 1)[1].strip()
        else:
            print(f'unexpected line {line!r} on line {self.lineno}')
            print('expect #+title:, #+server:, #+name: lines at start of file')
            exit()
        if c.title and c.server and c.name:
            self.state = 0

    def on_test_name(self, line):
        self.next_name = line.split(':')[1].strip()
        assert self.next_name not in self.test_names, (
            'duplicate name {0!r} on line {1}'
            .format(self.next_name, self.lineno))
        self.test_names.append(self.next_name)

    def on_begin_test(self, _line):
        assert self.next_name != self.prev_name, (
            'missing or duplicate name for test on line {0}'
            .format(self.lineno))
        self.tests.append(OldTestDescription(self.next_name, []))
        self.focus = self.tests[-1].lines
        self.prev_name = self.next_name

    def on_test_code(self, line):
        self.focus.append(line)

    def on_end_test(self, line):
        pass

    # -- main public interface ----------------------------------

    def parse(self, path):
        """
        Generates a sequence of TestDescription named tuples:
        Format is: (name:Str, lines:[Str])
        """
        for line in open(path): self.on_line(line)
        self.challenge.tests = [parse_test(x) for x in self.tests]
        return self.challenge


def parse_test(test):
    lines = test.lines
    while lines and lines[-1].strip() == '':
        lines.pop()
    opcodes = {
        'title': None,
        'doc': [],
        'in': [],
        'out': [],
    }
    for line in lines:
        if line.startswith('#'): continue
        if '#' in line:                # strip trailing comments
            line = line[:line.find('#')]
        sline = line.strip()
        if sline.startswith('='):      # test title
            opcodes['title'] = sline[2:]
        elif sline.startswith(':'):    # test description
            opcodes['doc'].append(sline)
        elif sline.startswith('>'):    # input to send
            opcodes['in'].append(sline[1:].lstrip())
        else:                          # expected output
            opcodes['out'].append(sline)
    step = TestDescription(
        name=test.name,
        head=opcodes['title'],
        body='\n'.join(opcodes['doc']),
        ilines=opcodes['in'],
        olines=opcodes['out'])
    return step


def read_challenge(path):
    return TestReaderStateMachine().parse(path)


def tests(path=None):
    """
    Convenience function to instantiate a TestReaderStateMachine
    and invoke .extract_tests on the given path.
    """
    if path is None:
        path = os.path.join(os.path.dirname(__file__), 'testplan.org')
    return read_challenge(path).tests


def main():
    if not os.path.exists('tests'): os.mkdir('tests')
    for i, test in enumerate(tests()):
        path = 'tests/test{0:03}.txt'.format(i)
        print("generating '{0}' in {1}"
              .format(test.name, path))
        io = open(path, 'w')
        for line in test.lines:
            io.write(line)
        io.close()


if __name__ == '__main__':
    main()
