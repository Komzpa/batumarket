"""Generate a GraphViz call graph of project functions and CLI entrypoints."""

import ast
import glob
import os

from graphviz import Digraph

# Collect function definitions across modules.
func_defs: dict[str, ast.FunctionDef] = {}
by_name: dict[str, set[str]] = {}
docstrings: dict[str, str] = {}
entrypoints: dict[str, list[ast.stmt]] = {}

for path in glob.glob("src/*.py"):
    module = os.path.splitext(os.path.basename(path))[0]
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            qname = f"{module}.{node.name}"
            func_defs[qname] = node
            by_name.setdefault(node.name, set()).add(qname)
            docstrings[qname] = ast.get_docstring(node) or ""
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
    dot.node(qname, shape="box", tooltip=docstrings.get(qname, ""))
for src, dst in sorted(edges):
    dot.edge(src, dst)

# Output DOT markup so ``dot`` can render an SVG later.
print(dot.source)
