from dataclasses import dataclass

@dataclass
class TestDescription:
    name: str
    head: str
    body: str
    ilines: [str]
    olines: [str]
