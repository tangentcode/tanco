from dataclasses import dataclass, field


@dataclass
class TestDescription:
    name: str = ''
    head: str = ''
    body: str = ''
    ilines: [str] = field(default_factory=list)
    olines: [str] = field(default_factory=list)


@dataclass
class Challenge:
    name: str = ''
    url: str = ''
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
    challenge_url: str = ''

    @staticmethod
    def default_target(self):
        return DEFAULT_TARGET

