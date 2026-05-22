"""Verify Sphinx reST docstrings on Python classes and callables.

Run from the repository root::

    uv run python scripts/check_rest_docstrings.py

The checker enforces the project policy (ADR-0010, user coding standards):

* Every class, function, and method has a non-empty docstring.
* Every parameter except ``self`` / ``cls`` is documented with ``:param name:``.
* Callables with a non-``None`` return annotation document ``:return:`` (or
  ``:returns:``).
* Generator-style callables (``Generator``, ``AsyncGenerator``, …) document
  ``:yields:`` instead of ``:return:`` when they yield values.

Exits with code ``1`` and a symbol-by-symbol report when any rule is violated.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = (ROOT / "backend", ROOT / "cli", ROOT / "scripts")
SKIP_DIR_NAMES = frozenset({".venv", "__pycache__", ".git", "venv"})
SKIP_PATH_FRAGMENTS = ("migrations/versions",)

PARAM_RE = re.compile(r":param\s+(\w+):")
RETURN_RE = re.compile(r":returns?:", re.IGNORECASE)
YIELDS_RE = re.compile(r":yields?:", re.IGNORECASE)
GENERATOR_ANNOTATION = re.compile(
    r"\b(AsyncGenerator|AsyncIterator|Generator|Iterator)\b",
)

ViolationKind = Literal[
    "missing_docstring",
    "missing_param",
    "missing_return",
    "missing_yields",
]


@dataclass(frozen=True, slots=True)
class Violation:
    """One docstring policy violation at a source location."""

    path: Path
    lineno: int
    symbol: str
    kind: ViolationKind
    detail: str

    def format(self) -> str:
        """
        Render a single-line message for CI logs.

        :return: Human-readable violation description.
        """
        return f"{self.path}:{self.lineno}: {self.symbol}: {self.detail}"


def _type_name(annotation: ast.expr | None) -> str | None:
    """
    Serialize a function return or parameter annotation.

    :param annotation: AST annotation node, if present.

    :return: Unparsed annotation text, or ``None``.
    """
    if annotation is None:
        return None
    return ast.unparse(annotation)


def _collect_params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """
    List user-visible parameter names for a callable.

    :param node: Function or async-function AST node.

    :return: Parameter names excluding ``self`` and ``cls``.
    """
    params: list[str] = []
    args = node.args
    for arg in args.posonlyargs + args.args + args.kwonlyargs:
        if arg.arg not in {"self", "cls"}:
            params.append(arg.arg)
    return params


def _is_generator_return(annotation: str | None) -> bool:
    """
    Return whether the annotation denotes a generator-style callable.

    :param annotation: Unparsed return annotation text.

    :return: ``True`` when ``:yields:`` is expected instead of ``:return:``.
    """
    if annotation is None:
        return False
    return GENERATOR_ANNOTATION.search(annotation) is not None


def _check_callable(
    path: Path,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    qualname: str,
) -> list[Violation]:
    """
    Validate reST coverage for one function or method.

    :param path: Source file path.
    :param node: Callable AST node.
    :param qualname: Qualified name for error messages.

    :return: Violations found on this callable.
    """
    issues: list[Violation] = []
    doc = ast.get_docstring(node, clean=False)
    if doc is None or not doc.strip():
        issues.append(
            Violation(
                path=path,
                lineno=node.lineno,
                symbol=qualname,
                kind="missing_docstring",
                detail="missing docstring",
            ),
        )
        return issues

    params = _collect_params(node)
    if params:
        documented = set(PARAM_RE.findall(doc))
        missing = [name for name in params if name not in documented]
        if missing:
            issues.append(
                Violation(
                    path=path,
                    lineno=node.lineno,
                    symbol=qualname,
                    kind="missing_param",
                    detail=f"missing :param: for {missing!r}",
                ),
            )

    return_ann = _type_name(node.returns)
    if return_ann in (None, "None"):
        return issues

    if _is_generator_return(return_ann):
        if not YIELDS_RE.search(doc):
            issues.append(
                Violation(
                    path=path,
                    lineno=node.lineno,
                    symbol=qualname,
                    kind="missing_yields",
                    detail="missing :yields: (generator return annotation)",
                ),
            )
        return issues

    if not RETURN_RE.search(doc):
        issues.append(
            Violation(
                path=path,
                lineno=node.lineno,
                symbol=qualname,
                kind="missing_return",
                detail=f"missing :return: (annotated {return_ann!r})",
            ),
        )
    return issues


def _check_class(path: Path, node: ast.ClassDef, *, qualname: str) -> list[Violation]:
    """
    Validate that a class has a docstring.

    :param path: Source file path.
    :param node: Class AST node.
    :param qualname: Qualified name for error messages.

    :return: Violations found on this class.
    """
    doc = ast.get_docstring(node, clean=False)
    if doc is None or not doc.strip():
        return [
            Violation(
                path=path,
                lineno=node.lineno,
                symbol=qualname,
                kind="missing_docstring",
                detail="missing docstring",
            ),
        ]
    return []


def check_file(path: Path) -> list[Violation]:
    """
    Validate all classes and callables defined in ``path``.

    :param path: Python source file.

    :return: All violations in the file.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    rel = path.relative_to(ROOT)
    issues: list[Violation] = []

    class Visitor(ast.NodeVisitor):
        """Walk the module AST and collect docstring violations."""

        def __init__(self) -> None:
            """Initialize the qualified-name stack."""
            self._scope: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            """
            Check a class docstring and recurse into its body.

            :param node: Class definition node.
            """
            qualname = ".".join([*self._scope, node.name])
            issues.extend(_check_class(rel, node, qualname=qualname))
            self._scope.append(node.name)
            self.generic_visit(node)
            self._scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            """
            Check a function docstring and recurse into nested callables.

            :param node: Function definition node.
            """
            qualname = ".".join([*self._scope, node.name])
            issues.extend(_check_callable(rel, node, qualname=qualname))
            self._scope.append(node.name)
            self.generic_visit(node)
            self._scope.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            """
            Check an async function docstring and recurse into nested callables.

            :param node: Async function definition node.
            """
            qualname = ".".join([*self._scope, node.name])
            issues.extend(_check_callable(rel, node, qualname=qualname))
            self._scope.append(node.name)
            self.generic_visit(node)
            self._scope.pop()

    Visitor().visit(tree)
    return issues


def iter_python_files() -> list[Path]:
    """
    Enumerate Python files subject to the reST docstring policy.

    :return: Sorted list of paths under ``backend/``, ``cli/``, and ``scripts/``.
    """
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if any(fragment in path.as_posix() for fragment in SKIP_PATH_FRAGMENTS):
                continue
            files.append(path)
    return files


def main() -> int:
    """
    Run the reST docstring policy across the workspace.

    :return: ``0`` when all symbols comply, ``1`` otherwise.
    """
    violations: list[Violation] = []
    for path in iter_python_files():
        violations.extend(check_file(path))

    if violations:
        for violation in violations:
            print(violation.format())
        print(f"\n{len(violations)} reST docstring violation(s).")
        return 1

    print("All docstrings satisfy the reST policy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
