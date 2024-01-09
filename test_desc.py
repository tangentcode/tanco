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
