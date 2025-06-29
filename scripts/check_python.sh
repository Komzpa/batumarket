#!/bin/sh
# Simple check script compiling all python files
echo 1000 > /proc/self/oom_score_adj 2>/dev/null || true
set -e
python -m py_compile "$@"
