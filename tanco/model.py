import difflib
import json
from dataclasses import dataclass, field
from enum import Enum

ResultKind = Enum('ResultKind', 'Pass Fail AskServer')


class ValidationRule:
    def to_data(self):
        raise NotImplementedError()

    @staticmethod
    def from_data(data):
        match data['kind']:
            case 'lines': return LineDiffRule(data['data'])
            case _: raise ValueError(f"unknown rule kind: {data['kind']}")

    @staticmethod
    def from_json(jsn: str) -> 'ValidationRule':
        return ValidationRule.from_data(json.loads(jsn))


class LineDiffRule(ValidationRule):

    def __init__(self, expected: [str]):
        self.expected = expected

    def to_data(self):
        return {'kind': 'lines', 'data': self.expected}


class TestFailure(AssertionError):
    pass


class LineDiffFailure(TestFailure):

    def __init__(self, diff: [str]):
        self.diff = diff

    @staticmethod
    def from_lines(actual: [str], expected: [str]):
        return LineDiffFailure(list(difflib.Differ().compare(actual, expected)))

    def to_data(self):
        return {
            'kind': 'diff',
            'data': self.diff}

    def print_error(self):
        print("---- how to patch your output to pass the test ----")
        diff = '\n'.join(self.diff)
        print(diff)


@dataclass
class TestResult:
    kind: ResultKind
    error: TestFailure = None
    rule: ValidationRule = None

    @staticmethod
    def from_data(data: dict) -> 'TestResult':

        res = TestResult(kind=ResultKind[data['kind']])
        match res.kind:
            case ResultKind.AskServer: raise RecursionError()
            case ResultKind.Fail:
                err = data['error']
                match err['kind']:
                    case 'diff': res.error = LineDiffFailure(diff=err['data'])
                    case _: raise ValueError(f"unknown error kind: {err['kind']}")
            case ResultKind.Pass:
                rule = data['rule']
                match rule['kind']:
                    case 'lines': res.rule = LineDiffRule(rule['data'])
                    case _: raise ValueError(f"unknown rule kind: {rule['kind']}")
        return res

    def to_data(self):
        """return raw data for json serialization"""
        kind = self.kind.name
        match kind:
            case 'Fail': return {'kind': kind, 'error': self.error.to_data()}
            case 'Pass': return {'kind': kind, 'rule': self.rule.to_data()}
            case 'AskServer': raise NotImplementedError()

    def is_pass(self):
        return self.kind == ResultKind.Pass


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

    @property
    def rule(self) -> ValidationRule:
        if self.olines is None:
            return None
        else:
            return LineDiffRule(self.olines)

    def check_output(self, actual: [str]) -> TestResult:
        if self.olines is None:
            return TestResult(ResultKind.AskServer)
        elif self.olines == actual:
            rule = LineDiffRule(self.olines)
            return TestResult(ResultKind.Pass, rule=rule)
        else:
            e = LineDiffFailure.from_lines(actual=actual, expected=self.olines)
            return TestResult(ResultKind.Fail, error=e)


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