import difflib
import json
from dataclasses import dataclass, field
from enum import Enum

ResultKind = Enum('ResultKind', 'Pass Fail AskServer')
Transition = Enum('Transition', 'Pass Next Fail')
AttemptState = Enum('AttemptState', 'Start Build Fix Change Done')


class ValidationRule:
    def to_data(self):
        raise NotImplementedError

    @staticmethod
    def from_data(data):
        match data['kind']:
            case 'lines': return LineDiffRule(data['data'])
            case _: raise ValueError(f"unknown rule kind: {data['kind']}")

    @staticmethod
    def from_json(jsn: str) -> 'ValidationRule':
        return ValidationRule.from_data(json.loads(jsn))


class LineDiffRule(ValidationRule):

    def __init__(self, expected: list[str]):
        self.expected = expected

    def to_data(self):
        return {'kind': 'lines', 'data': self.expected}


class TestFailure(AssertionError):
    def error_lines(self):
        raise NotImplementedError

    def print_error(self):
        for line in self.error_lines():
            print(line)


class LineDiffFailure(TestFailure):

    def __init__(self, actual: list[str], diff: list[str]):
        self.actual = actual
        self.diff = diff

    @staticmethod
    def from_lines(actual: list[str], expected: list[str]):
        return LineDiffFailure(actual, list(difflib.Differ().compare(actual, expected)))

    @staticmethod
    def from_data(data: dict) -> 'LineDiffFailure':
        return LineDiffFailure(data['actual'], data['diff'])

    def to_data(self):
        return {
            'kind': 'diff',
            'data': {'actual': self.actual, 'diff': self.diff}}

    def error_lines(self):
        return (['---- how to patch your output to pass the test ----', *self.diff])


@dataclass
class TestResult:
    kind: ResultKind
    error: TestFailure = None
    rule: ValidationRule = None
    actual: list[str] = field(default_factory=list)

    @staticmethod
    def from_data(data: dict) -> 'TestResult':
        res = TestResult(kind=ResultKind[data['kind']])
        match res.kind:
            case ResultKind.AskServer: raise RecursionError
            case ResultKind.Fail:
                err = data['error']
                match err['kind']:
                    case 'diff': res.error = LineDiffFailure.from_data(err['data'])
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
            case 'Fail': return {'kind': kind, 'actual': self.actual,
                                 'error': self.error.to_data()}
            case 'Pass': return {'kind': kind, 'rule': self.rule.to_data()}
            case 'AskServer': raise NotImplementedError

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
    ilines: list[str] = field(default_factory=list)
    olines: list[str] = field(default_factory=list)

    @property
    def rule(self) -> ValidationRule | None:
        if self.olines is None:
            return None
        else:
            return LineDiffRule(self.olines)

    def check_output(self, actual: list[str]) -> TestResult:
        if self.olines is None:
            return TestResult(ResultKind.AskServer)
        elif self.olines == actual:
            rule = LineDiffRule(self.olines)
            return TestResult(ResultKind.Pass, rule=rule)
        else:
            e = LineDiffFailure.from_lines(actual=actual, expected=self.olines)
            return TestResult(ResultKind.Fail, error=e, actual=actual)


@dataclass
class Challenge:
    id: int = 0
    sid: int = 0
    name: str = ''
    server: str = ''
    title: str = ''
    tests: list[TestDescription] = field(default_factory=list)


DEFAULT_TARGET = './my-program'


@dataclass
class Config:
    uid: int = 0
    program_args: list[str] = field(default_factory=lambda: [DEFAULT_TARGET])
    use_shell: bool = False
    # where to write the input to the child program
    # (for cases where stdin is not available)
    input_path: str = ''
    # path to test plan (if running directly from org file)
    test_plan: str | None = ''
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
