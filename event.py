OPEN = 1
CLOSE = 2

names = [None, 'OPEN', 'CLOSE']

class Event:
    def __init__(self, kind: int, gid: int, name: str = None):
        self.kind = kind # OPEN, CLOSE
        self.gid = gid
        self.name = name

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f"Event({names[self.kind]} {self.gid}{'' if not self.name else ' ' + self.name})"

    def __eq__(self, other):
        return self.kind == other.kind and self.gid == other.gid

    def __hash__(self):
        return hash((self.kind, self.gid))