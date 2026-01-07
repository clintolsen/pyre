#
# util.py
#

# Make the following text reverse video
#
def highlight(data):
    return '\033[07m' + data + '\033[0m'
