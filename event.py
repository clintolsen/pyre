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

    # The name is part of identity: markers are interned by their events, so
    # ignoring it would let one pattern's group name leak into another's.
    #
    def __eq__(self, other):
        return (self.kind, self.gid, self.name) == (other.kind, other.gid, other.name)

    def __hash__(self):
        return hash((self.kind, self.gid, self.name))