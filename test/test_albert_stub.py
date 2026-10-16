"""The type stub and the runtime double must agree.

`stubs/albert/__init__.pyi` is what mypy reads; `test/albert_stub.py` is what
pytest imports. They stand in for the same module, and a plugin is checked
against one while being run against the other. If they drift, a plugin passes
tests that a real launcher would refuse, or passes mypy and fails at runtime -
and nothing else in the suite would notice.

Three properties are asserted here, chosen because each one has actually broken
during this work:

1. Every name any plugin does `from albert import <name>` must exist in the
   runtime double. That is the one that matters most, and it is why the
   conftest installs a deliberately strict stub that raises AttributeError for
   anything unknown.
2. The same names must exist in the type stub, or mypy is checking a plugin
   against an API the launcher does not have.
3. The logging helpers must NOT be attributes of the runtime double, and must
   NOT be in the type stub. The launcher attaches them to the plugin's own
   module (py::setattr in pypluginloader.cpp), not to `albert`, so a plugin
   that does `from albert import debug` is broken on a real install. Upstream's
   hand-written albert.pyi lists them as members and is wrong about that.
"""

import ast
import sys
from pathlib import Path
from typing import Dict, List, Set

import pytest

REPO_ROOT = Path(__file__).parent.parent
STUB_FILE = REPO_ROOT / "stubs" / "albert" / "__init__.pyi"
RUNTIME_STUB = Path(__file__).parent / "albert_stub.py"

LOGGING_GLOBALS = ("debug", "info", "warning", "critical")


def _stub_tree() -> ast.Module:
    return ast.parse(STUB_FILE.read_text())


def _stub_names() -> Set[str]:
    """Public names the .pyi defines, ignoring the typing imports it needs."""
    names: Set[str] = set()
    for node in _stub_tree().body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(a.asname or a.name.split(".")[0] for a in node.names)
    return names - {"annotations"}


def _imported_names() -> Dict[str, Set[str]]:
    """Every name any plugin imports from `albert`, plus where it is imported."""
    found: Dict[str, Set[str]] = {}
    inits: List[Path] = sorted((REPO_ROOT / "plugins").glob("*/__init__.py"))
    for init in inits:
        try:
            tree = ast.parse(init.read_text())
        except SyntaxError:  # pragma: no cover - a plugin that won't parse
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "albert":
                for alias in node.names:
                    found.setdefault(alias.name, set()).add(init.parent.name)
    return found


def _runtime_names() -> Set[str]:
    return {n for n in dir(sys.modules["albert"]) if not n.startswith("_")}


def _runtime_own_names() -> Set[str]:
    """The double's own machinery: its imports and its module-level constants.

    These are not part of the albert API, so the type stub is not expected to
    declare them. Derived from the source rather than hardcoded, so adding an
    import to the double does not turn this into a failing test.
    """
    own: Set[str] = set()
    for node in ast.parse(RUNTIME_STUB.read_text()).body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            own.update(a.asname or a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.Assign):
            own.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return own


IMPORTED = _imported_names()


def test_stub_files_exist():
    assert STUB_FILE.is_file(), f"missing type stub: {STUB_FILE}"
    assert RUNTIME_STUB.is_file(), f"missing runtime double: {RUNTIME_STUB}"


def test_plugins_do_import_albert():
    """Guards the tests above: an empty scan would pass them all vacuously."""
    assert len(IMPORTED) >= 9, (
        f"only found {len(IMPORTED)} names imported from albert; "
        "the ast scan is broken, not the plugins"
    )


@pytest.mark.parametrize("name", sorted(IMPORTED))
def test_name_exists_in_runtime_stub(name):
    plugins = ", ".join(sorted(IMPORTED[name]))
    assert name in _runtime_names(), (
        f"{plugins} import {name} from albert, but the runtime double does not "
        "have it: the plugin would fail on a real launcher"
    )


@pytest.mark.parametrize("name", sorted(IMPORTED))
def test_name_exists_in_type_stub(name):
    plugins = ", ".join(sorted(IMPORTED[name]))
    assert name in _stub_names(), (
        f"{plugins} import {name} from albert, but stubs/albert/__init__.pyi "
        "does not declare it: mypy is checking against an API that is not there"
    )


@pytest.mark.parametrize("name", LOGGING_GLOBALS)
def test_logging_globals_are_not_albert_members(name):
    """The loader sets these on the plugin module, not on `albert`."""
    assert name not in _runtime_names(), (
        f"albert.{name} must not exist: the launcher attaches the logging "
        "helpers to the plugin's own module, so `from albert import debug` "
        "works in the mock and breaks on a real install"
    )
    assert name not in _stub_names(), (
        f"stubs/albert declares {name}; it must not, for the same reason"
    )


def test_logging_globals_are_injected_into_plugins():
    """The complement: a plugin can call them anyway, because the loader does it."""
    from conftest import load_plugin

    plugin = load_plugin("dockge")
    for name in LOGGING_GLOBALS:
        assert callable(getattr(plugin, name)), f"{name} was not injected"
    assert plugin.__name__.endswith("dockge") or "dockge" in plugin.__name__


def test_type_stub_covers_the_runtime_api():
    """Every runtime name a plugin could use is also declared in the .pyi.

    The .pyi is allowed to declare more (Protocols that never exist at runtime,
    and the typing names it needs). It is not allowed to be missing something
    the runtime double offers, since that combination type-checks clean and then
    fails in a test.
    """
    missing = _runtime_names() - _stub_names() - _runtime_own_names()
    assert not missing, (
        f"runtime double defines names the type stub omits: {sorted(missing)}"
    )
