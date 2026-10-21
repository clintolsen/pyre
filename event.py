import itertools

OPEN = 1
CLOSE = 2

names = [None, 'OPEN', 'CLOSE']

class Source:
    """
    One parsed pattern string. A group id is (source, index), where index
    is the position of the group's '(' in that string, counted from 1, and
    count is how many groups the string has. Groups from separately parsed
    patterns never collide, and a group keeps its number even if its
    markers are simplified away, as in (a){0}.
    """
    _serials = itertools.count(1)

    def __init__(self):
        self.serial = next(Source._serials)
        self.count = 0

    def __repr__(self):
        return f'p{self.serial}'

class Event:
    def __init__(self, kind: int, gid: tuple, name: str = None):
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