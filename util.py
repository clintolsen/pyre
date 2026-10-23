#
# util.py
#

# Make the following text reverse video
#
def highlight(data):
    if isinstance(data, bytes):
        return b'\033[07m' + data + b'\033[0m'
    return '\033[07m' + data + '\033[0m'
