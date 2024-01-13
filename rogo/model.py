import difflib
import json
from dataclasses import dataclass, field
from enum import Enum

ResultKind = Enum('ResultKind', 'Pass Fail AskServer')


class TestFailure(AssertionError):
    pass


class LineDiffFailure(TestFailure):
    def __init__(self, expected: [str], actual: [str]):
        self.expected = expected
        self.actual = actual

    def print_error(self):
        print()
        print("---- expected results ----")
        print('\n'.join(self.expected))
        print("---- how to patch your output to pass the test ----")
        diff = '\n'.join(list(difflib.Differ().compare(self.actual, self.expected)))
        print(diff)


@dataclass
class TestResult:
    kind: ResultKind
    error: TestFailure = None
    rule: str = None


@dataclass
class TestDescription:
    id: int = 0
    chid: int = 0
    grp: int = 0
    ord: int = 0
    name: str = ''
    head: str = ''
    body: str = ''
    ilines: [str] = field(default_factory=list)
    olines: [str] = field(default_factory=list)
    rule: str = ''

    def check_output(self, actual: [str]) -> TestResult:
        if self.olines is None:
            return TestResult(ResultKind.AskServer)
        elif self.olines == actual:
            return TestResult(ResultKind.Pass)
        else:
            return TestResult(ResultKind.Fail,
                              error=LineDiffFailure(
                                  expected=self.olines,
                                  actual=actual))


@dataclass
class Challenge:
    id: int = 0
    sid: int = 0
    name: str = ''
    server: str = ''
    title: str = ''
    tests: [TestDescription] = field(default_factory=list)


DEFAULT_TARGET = './my-program'


@dataclass
class Config:
    program_args: [str] = field(default_factory=lambda: [DEFAULT_TARGET])
    use_shell: bool = False
    # where to write the input to the child program
    # (for cases where stdin is not available)
    input_path: str = ''
    # path to test plan (if running directly from org file)
    test_plan: str = ''
    # skip this many lines of input before sending
    # for cases where the language prints a header
    # that can't be suppressed. (e.g. Godot4 - you can turn
    # off the header, but doing so turns off all prints!)
    skip_lines: int = 0
    attempt: str = ''

    @staticmethod
    def default_target():
        return DEFAULT_TARGET

    def to_json(self):
        data = {
            'attempt': self.attempt,
            'targets': {
                'main': {
                    'args': self.program_args,
                    'shell': self.use_shell}}}
        return json.dumps(data, indent=2)
