#
# util.py
#

# Make the following text reverse video
#
def highlight(data):
    if isinstance(data, bytes):
        return b'\033[07m' + data + b'\033[0m'
    return '\033[07m' + data + '\033[0m'


# Line and column of text[pos], both counted from 1, for error messages
#
def line_col(text, pos):
    newline = '\n' if isinstance(text, str) else b'\n'
    return text.count(newline, 0, pos) + 1, pos - text.rfind(newline, 0, pos)
