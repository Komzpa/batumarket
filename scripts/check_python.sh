#!/bin/sh
# Simple check script compiling all python files
set -e
python -m py_compile "$@"
