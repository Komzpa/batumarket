"""Generate a GraphViz call graph of project functions."""

import ast
import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from oom_utils import prefer_oom_kill

prefer_oom_kill()

from graphviz import Digraph
import math

# Collect function definitions across modules.
# ``AsyncFunctionDef`` nodes were previously ignored which meant ``tg_client``
# functions like ``main`` did not appear in the diagram.
func_defs: dict[str, ast.AST] = {}
by_name: dict[str, set[str]] = {}
docstrings: dict[str, str] = {}
entrypoints: dict[str, list[ast.stmt]] = {}
sizes: dict[str, int] = {}

for path in glob.glob("src/*.py") + glob.glob("scripts/*.py"):
    module = os.path.splitext(os.path.basename(path))[0]
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src, filename=path)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qname = f"{module}.{node.name}"
            func_defs[qname] = node
            by_name.setdefault(node.name, set()).add(qname)
            docstrings[qname] = ast.get_docstring(node) or ""
            size = getattr(node, "end_lineno", node.lineno) - node.lineno + 1
            sizes[qname] = max(1, size)
        elif (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
            and any(
                isinstance(c, ast.Constant) and c.value == "__main__"
                for c in node.test.comparators
            )
        ):
            entrypoints[f"{module}:cli"] = node.body
            docstrings[f"{module}:cli"] = "Command line entrypoint"
            if node.body:
                size = getattr(node.body[-1], "end_lineno", node.body[-1].lineno) - node.body[0].lineno + 1
            else:
                size = 1
            sizes[f"{module}:cli"] = size

# Build edges between functions and from entrypoints.
edges = set()
all_defs: dict[str, ast.AST] = {
    **func_defs,
    **{k: ast.Module(body=v, type_ignores=[]) for k, v in entrypoints.items()},
}

for qname, node in all_defs.items():
    module = qname.split(".")[0].split(":")[0]
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
                candidate = f"{module}.{name}"
                if candidate in func_defs:
                    edges.add((qname, candidate))
                    continue
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name and name in by_name:
                targets = by_name[name]
                if len(targets) == 1:
                    edges.add((qname, next(iter(targets))))

# Render the graph using the ``graphviz`` library.
dot = Digraph("callgraph", graph_attr={"rankdir": "LR"})

for qname in all_defs:
    size = sizes.get(qname, 1)
    scale = max(0.5, round(math.sqrt(size) / 2, 2))
    shape = "ellipse" if qname.endswith(":cli") else "box"
    dot.node(
        qname,
        shape=shape,
        tooltip=docstrings.get(qname, ""),
        fontsize=str(round(14 * scale, 2)),
    )

for src, dst in sorted(edges):
    dot.edge(src, dst)

# Output DOT markup so ``dot`` can render an SVG later.
print(dot.source)
