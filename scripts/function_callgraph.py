"""Generate a GraphViz call graph of project functions."""

import ast
import glob
import os

from graphviz import Digraph

# Collect function definitions across modules.
func_defs: dict[str, ast.FunctionDef] = {}
by_name: dict[str, set[str]] = {}
for path in glob.glob("src/*.py"):
    module = os.path.splitext(os.path.basename(path))[0]
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            qname = f"{module}.{node.name}"
            func_defs[qname] = node
            by_name.setdefault(node.name, set()).add(qname)

# Build edges between functions
edges = set()
for qname, node in func_defs.items():
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name and name in by_name:
                for target in by_name[name]:
                    edges.add((qname, target))

# Render the graph using the ``graphviz`` library.
dot = Digraph("callgraph")
for qname in func_defs:
    dot.node(qname, shape="box")
for src, dst in sorted(edges):
    dot.edge(src, dst)

# Output DOT markup so ``dot`` can render an SVG later.
print(dot.source)
