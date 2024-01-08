from dataclasses import dataclass

@dataclass
class TestStep:
    name: str
    head: str
    body: str
    ilines: [str]
    olines: [str]
