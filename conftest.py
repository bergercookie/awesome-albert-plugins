"""Root conftest: make `import albert` work for tests run outside Albert.

Every plugin does `from albert import ...` at module scope, and the `albert`
module only exists inside the running launcher. Without a stand-in, not one
plugin in this repo can be imported by pytest, so a plugin's own tests could
never run.

Two things are installed here, both before any test collection:

1. `test/albert_stub.py` is registered in `sys.modules` as `albert`, so plugin
   imports resolve. The stub is deliberately strict: anything not in the v5.0
   API raises AttributeError, so a plugin using a removed name fails here the
   same way it fails in a real launcher.

2. The four logging functions are attached to each plugin module as it is
   loaded, mirroring what the real loader does. The launcher does

       py::setattr(module_, "critical", ...)

   in albert-plugin-python's src/pypluginloader.cpp, just before exec_module,
   so `critical` is a bare global inside a plugin and NOT an attribute of
   `albert`. `load_plugin()` below is the only supported way to import one.

Note `albert.pyi` in the upstream stub repo lists these as members of `albert`;
it is hand-written and wrong about that. `just` never installs it.
"""

import importlib.machinery
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent
PLUGINS_DIR = REPO_ROOT / "plugins"

# ---------------------------------------------------------------- the albert module

if "albert" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "albert", Path(__file__).parent / "test" / "albert_stub.py"
    )
    assert _spec and _spec.loader
    _albert = importlib.util.module_from_spec(_spec)
    sys.modules["albert"] = _albert
    _spec.loader.exec_module(_albert)


# ------------------------------------------------ third-party deps we can't install

# Each plugin declares its own md_lib_dependencies and is installed into its own
# venv by the launcher, so there is no single environment with all of them (and
# some -- netifaces, pulsectl -- need system headers). Anything absent is
# replaced by a permissive recording stub so the plugin can still be imported and
# its own logic tested. A test that needs the real library should say so via
# pytest.importorskip rather than silently running against a mock.
# Import names, not distribution names: Pillow->PIL, beautifulsoup4->bs4,
# em-keyboard->em.keyboard, python-dateutil->dateutil. Every one of these is
# declared in some plugin's md_lib_dependencies.
_UNAVAILABLE = {
    "PyDictionary",
    "PIL",
    "bs4",
    "colour",
    "dateutil",
    "em",
    "fuzzywuzzy",
    "gi",
    "httpx",
    "jira",
    "lxml",
    "matplotlib",
    "netifaces",
    "numpy",
    "psutil",
    "pulsectl",
    "pycountry",
    "pytz",
    "requests",
    "syncall",
    "taskw",
    "thefuzz",
    "totp",
    "tzlocal",
    "vcfxplr",
}


class _StubModule(types.ModuleType):
    """A module whose every attribute is an auto-recording stand-in."""

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        stub = _StubModule(f"{self.__name__}.{name}")
        stub.__path__ = []
        setattr(self, name, stub)
        return stub

    def __call__(self, *args, **kwargs):
        return _StubModule(f"{self.__name__}()")


class _StubLoader:
    def create_module(self, spec):
        module = _StubModule(spec.name)
        module.__path__ = []
        module.__is_albert_stub__ = True
        return module

    def exec_module(self, module):
        if module.__name__ == "gi":
            module.require_version = lambda *a, **k: None
            module.require_foreign = lambda *a, **k: None


def _is_installed(root: str) -> bool:
    """True if *root* is importable from sys.path, ignoring our own finder.

    Queries PathFinder (the sys.path finder) directly rather than going
    through importlib.util, which would re-enter this finder and recurse, and
    rather than iterating sys.meta_path, whose legacy find_module-only finders
    take no path argument.
    """
    try:
        spec = importlib.machinery.PathFinder.find_spec(root, None)
    except (ImportError, ValueError):
        return False
    return spec is not None


class _StubFinder:
    """Only claims a module that is genuinely not installed."""

    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root not in _UNAVAILABLE:
            return None
        # Never shadow something the environment really has: pytest must fail
        # loudly on a broken real install rather than quietly test a mock.
        # Ask the *path* finders directly -- going through importlib.util would
        # re-enter this finder and recurse.
        if root not in sys.modules and _is_installed(root):
            return None
        return importlib.machinery.ModuleSpec(fullname, _StubLoader(), is_package=True)


if not any(isinstance(f, _StubFinder) for f in sys.meta_path):
    sys.meta_path.append(_StubFinder())


# ---------------------------------------------------------------- plugin loading

#: Names the real loader attaches to every plugin module. See module docstring.
_LOGGING_GLOBALS = ("debug", "info", "warning", "critical")


def load_plugin(name: str) -> types.ModuleType:
    """Import plugins/<name>/__init__.py the way the launcher does.

    The four logging functions are attached to the module before execution,
    which is what makes a bare `critical(...)` call inside a plugin valid.

    `addopts` includes `--doctest-modules`, so collection imports every
    ``plugins/<name>/__init__.py`` itself, under the bare name ``<name>`` and
    with no loader attached. Reuse that module when it is already there, but
    still attach the logging globals -- a cached hit must not be the one way to
    get a plugin that explodes on the first `debug(...)`.
    """
    if name in sys.modules:
        module = sys.modules[name]
    else:
        init = PLUGINS_DIR / name / "__init__.py"
        if not init.is_file():
            raise ImportError(f"no such plugin: {name} (looked for {init})")

        spec = importlib.util.spec_from_file_location(f"albertplug_{name}", init)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module

        spec.loader.exec_module(module)

    for fn in _LOGGING_GLOBALS:
        setattr(module, fn, _log_recorder(name, fn))

    return module


def load_plugin_from(init: Path, name: str) -> types.ModuleType:
    """Import a plugin's ``__init__.py`` from an arbitrary path.

    Same contract as :func:`load_plugin`, for a plugin that does not live under
    ``plugins/`` -- the copy a built Debian package installed, say. A distinct
    module name is used so importing the installed copy never collides with the
    source-tree module pytest already collected, and the file is loaded as a
    package so a plugin that keeps helper modules next to ``__init__.py`` (e.g.
    ``image_search/bing.py``) still finds them.
    """
    init = Path(init)
    spec = importlib.util.spec_from_file_location(
        f"albertplug_installed_{name}",
        init,
        submodule_search_locations=[str(init.parent)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module

    spec.loader.exec_module(module)

    for fn in _LOGGING_GLOBALS:
        setattr(module, fn, _log_recorder(name, fn))

    return module


def _log_recorder(plugin: str, level: str):
    def _log(message):
        albert = sys.modules["albert"]
        albert._LOGS.append((f"{plugin}:{level}", str(message)))

    return _log


@pytest.fixture
def plugin(request):
    """Load the plugin named by the test, e.g. `def test_x(plugin):` for 'x'.

    Plugins whose own deps are missing are skipped rather than failed, so a
    contributor without, say, netifaces installed can still run the suite.
    """
    name = getattr(request, "param", None) or request.module.__name__.rsplit(".", 1)[-1]
    try:
        return load_plugin(name)
    except ImportError as e:
        if name in _UNAVAILABLE or "No module named" in str(e):
            pytest.skip(f"{name}: dependency unavailable ({e})")
        raise


def pytest_addoption(parser):
    # addoption is only legal on the parser, and only before pytest_configure
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="Also run the tests marked `network`, which reach out to the internet.",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "network: test needs internet access (deselected by default)"
    )


def pytest_collection_modifyitems(config, items):
    """Keep the network tests out of a default run.

    A sandbox, a plane and an offline CI machine all look the same to pytest: the
    request raises or comes back 403, and the suite reports a failure that has
    nothing to do with the code. `just test` stays green without them; ask for
    them with `just test-network` when the links are what you actually care
    about.
    """
    if config.getoption("--run-network"):
        return

    skip = pytest.mark.skip(reason="needs internet access; pass --run-network to include it")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)
