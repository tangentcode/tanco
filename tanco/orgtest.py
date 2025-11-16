"""
Implements a finite state machine to extract tanco
test descriptions from org files.

The org file format is described here:

  http://orgmode.org/worg/dev/org-syntax.html

However, there is no need to fully parse the outline
structure, since we are only interested in the actual
test cases, and these are clearly marked off by lines
in the following format:

Format v0.1 (legacy):
   #+name: testname
   #+begin_src
    <test code winds up here>
    = title
    : description lines
   #+end_src

Format v0.2 (current):
   ** TEST testname : title
   #+begin_src
    <test code winds up here>
   #+end_src

   Description lines appear here as plain text.

Test lines are simple sequences of lines in the
following format:

- Lines that begin with ">" are input lines.
  The test runner will send these to your program.

- The "#" character indicates a comment, which is
  shown to the user but not part of the expected
  output.

- The "\" character can be used to escape any of
  these special characters (including itself).

"""
import os
import re
from collections import namedtuple

from .model import Challenge, TestDescription

# For v0.1 compatibility
OldTestDescription = namedtuple('OldTestDescription', ['name', 'lines'])

# Mutable test container for v0.2 (allows adding title and body_lines attributes)
class TestContainer:
    def __init__(self, name, lines):
        self.name = name
        self.lines = lines
        self.title = None
        self.body_lines = []


class TestReaderStateMachine:
    """
    A simple finite state machine to extract tests from an outline.
    Supports both v0.1 (#+name: + = and : prefixes) and v0.2 (TEST headlines) formats.
    """
    def __init__(self):
        self.states = [ # NOTE: this is ordered and first field should == index
            (0, self.do_nothing),
            (1, self.on_test_code),
            (2, self.on_meta_line),
            (3, self.on_body_text)]  # v0.2: collecting text after #+end_src
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

        # v0.2 format support
        self.format_version = '0.1'  # default to legacy format
        self.current_headline = None  # track current headline for v0.2
        self.current_test_name = None  # test name from headline
        self.current_test_title = None  # test title from headline
        self.body_lines = []  # collect body text after #+end_src in v0.2
        self.test_headline_pattern = re.compile(
            r'^\*+\s*(?:TODO|DONE)?\s*TEST\s+([\w.\-]+)\s*(?::\s*(.+))?$'
        )

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

        # Detect format version
        if line.startswith('#+tanco-format:'):
            self.format_version = line.split(':', 1)[1].strip()

        # Handle metadata directives
        if line.startswith('#+title:'):
            c.title = line.split(':', 1)[1].strip()
        elif line.startswith('#+server:'):
            c.server = line.split(' ', 1)[1].strip()
        elif line.startswith('#+name:'):
            name_value = line.split(':', 1)[1].strip()
            # In v0.2, #+name: at file level is challenge name (test names come from TEST headlines)
            if self.format_version == '0.2':
                if not c.name:
                    c.name = name_value
                # Don't call on_test_name or change state - just ignore test-level #+name: in v0.2
            else:
                # v0.1 format: #+name: could be challenge name or test name
                if c.name:
                    # Already have challenge name, so this is a test name
                    self.state = 0
                    self.on_test_name(line)
                else:
                    # First #+name: might be challenge name
                    c.name = name_value
                    self.state = 0
                    # Also set as test name in case it's actually a test
                    self.on_test_name(line)

        # v0.2: Check for TEST headlines
        elif self.format_version == '0.2' and line.startswith('*'):
            match = self.test_headline_pattern.match(line.rstrip())
            if match:
                test_name = match.group(1)
                test_title = match.group(2) if match.group(2) else None
                self.current_test_name = test_name
                self.current_test_title = test_title
                self.current_headline = line.rstrip()
                # Transition to state 0 to look for #+begin_src
                self.state = 0

        # Allow other lines - they might be comments or other org content
        elif not line.strip():  # Empty lines are fine
            pass
        elif line.startswith('#'):  # Other org directives are fine
            pass
        else:  # Regular text is fine too
            pass

    def on_test_name(self, line):
        self.next_name = line.split(':')[1].strip()
        assert self.next_name not in self.test_names, (
            'duplicate name {0!r} on line {1}'
            .format(self.next_name, self.lineno))
        self.test_names.append(self.next_name)

    def on_begin_test(self, _line):
        # Determine test name based on format version
        if self.format_version == '0.2':
            # In v0.2, use name from TEST headline
            test_name = self.current_test_name
        else:
            # In v0.1, use name from #+name: directive
            test_name = self.next_name

        # Only start collecting test lines if we have a valid name
        if test_name and test_name != self.prev_name:
            # Check for duplicate names
            if test_name in self.test_names:
                raise AssertionError(
                    f'duplicate name {test_name!r} on line {self.lineno}'
                )
            self.test_names.append(test_name)

            # Use TestContainer for v0.2, OldTestDescription for v0.1
            if self.format_version == '0.2':
                self.tests.append(TestContainer(test_name, []))
            else:
                self.tests.append(OldTestDescription(test_name, []))

            self.focus = self.tests[-1].lines
            self.prev_name = test_name
        else:
            # If no name or duplicate name, ignore this block
            self.focus = None

    def on_test_code(self, line):
        # Only collect lines if we're in a valid test block
        if self.focus is not None:
            self.focus.append(line)

    def on_end_test(self, line):
        # Reset focus after ending a test block
        self.focus = None

        # In v0.2, transition to body text collection state
        if self.format_version == '0.2':
            self.state = 3  # Start collecting body text
            self.body_lines = []
        # In v0.1, go back to state 0 (already handled by transition table)

    def on_body_text(self, line):
        """Collect plain text after #+end_src in v0.2 format."""
        # Stop collecting when we hit a new headline or another test directive
        if line.startswith('*') or line.startswith('#+name:') or line.startswith('#+begin_src'):
            # Finalize current test with collected body
            self._finalize_v02_test()
            # Process this line in the appropriate state
            self.state = 2  # Back to meta state
            self.on_meta_line(line)
        else:
            # Collect body text (skip leading empty lines)
            if self.body_lines or line.strip():
                self.body_lines.append(line.rstrip())

    def _finalize_v02_test(self):
        """Finalize a v0.2 test by adding title and body from headline and collected text."""
        if not self.tests:
            return

        # Get the most recent test
        test = self.tests[-1]

        # Trim trailing empty lines from body
        while self.body_lines and not self.body_lines[-1]:
            self.body_lines.pop()

        # Store title and body for v0.2 tests
        # We'll handle this in parse_test_v02 function
        test.title = self.current_test_title
        test.body_lines = self.body_lines.copy()

        # Reset for next test
        self.current_test_name = None
        self.current_test_title = None
        self.body_lines = []

    # -- main public interface ----------------------------------

    def parse(self, path):
        """
        Generates a sequence of TestDescription named tuples:
        Format is: (name:Str, lines:[Str])
        """
        for line in open(path):
            self.on_line(line)

        # Finalize last test in v0.2 format if needed
        if self.format_version == '0.2' and self.state == 3:
            self._finalize_v02_test()

        # Parse tests based on format version
        if self.format_version == '0.2':
            self.challenge.tests = [parse_test_v02(x) for x in self.tests]
        else:
            self.challenge.tests = [parse_test_v01(x) for x in self.tests]

        return self.challenge


def parse_test_v01(test):
    """Parse a test in v0.1 format (with = and : prefix lines)."""
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


def parse_test_v02(test):
    """Parse a test in v0.2 format (title and body from headline and post-src text)."""
    lines = test.lines
    while lines and lines[-1].strip() == '':
        lines.pop()

    # In v0.2, no = or : lines to parse, just input/output
    opcodes = {
        'in': [],
        'out': [],
    }
    for line in lines:
        if line.startswith('#'): continue
        if '#' in line:                # strip trailing comments
            line = line[:line.find('#')]
        sline = line.strip()
        if sline.startswith('>'):      # input to send
            opcodes['in'].append(sline[1:].lstrip())
        else:                          # expected output
            opcodes['out'].append(sline)

    # Get title and body from test attributes (set by _finalize_v02_test)
    title = getattr(test, 'title', None)
    body_lines = getattr(test, 'body_lines', [])
    body = '\n'.join(body_lines)

    step = TestDescription(
        name=test.name,
        head=title,
        body=body,
        ilines=opcodes['in'],
        olines=opcodes['out'])
    return step


# Backward compatibility alias
def parse_test(test):
    """Parse a test (legacy function, assumes v0.1 format)."""
    return parse_test_v01(test)


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
