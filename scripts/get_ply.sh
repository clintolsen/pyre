#!/usr/bin/env sh
set -eu

ROOT="$(cd "$(dirname "$0")/.."; pwd)"
DEST="$ROOT/ply"
BASE="https://raw.githubusercontent.com/dabeaz/ply/master/src/ply"

mkdir -p "$DEST"

for f in __init__.py lex.py yacc.py; do
    echo "Downloading $f..."
    curl -fsSL "$BASE/$f" -o "$DEST/$f"
done

echo "PLY installed into $DEST"
