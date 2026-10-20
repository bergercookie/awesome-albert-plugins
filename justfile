# Linting and tests for every plugin in this repo at once.
#
#   just            list the recipes
#   just lint       ruff + mypy, what pre-commit runs
#   just test       pytest with doctests, no network
#   just check      lint + test, what you want before pushing
#   just deb        build the .deb that ships every plugin
#   just deb-smoke  build it, install it, import every plugin back
#
# Everything runs against the repo's own .venv. Plugins declare their own
# md_lib_dependencies and are installed into per-plugin venvs by the launcher,
# so there is deliberately no "install all dependencies" recipe here: the tools
# in .venv are the only third-party packages this repo's own code needs.
#
# devbox.json provisions the environment (just, python, dpkg, ...) and creates
# .venv on first entry, so `devbox shell` and CI run the same recipes below.

venv := ".venv"
python := venv / "bin/python"
ruff := venv / "bin/ruff"
mypy := venv / "bin/mypy"
pytest := venv / "bin/python -m pytest"

# List the recipes. `just` with no arguments does this.
default:
    @just --list --unsorted

# --- checks ---------------------------------------------------------------------

# Everything that has to pass before a change is worth pushing.
check: lint test

# What pre-commit enforces: the fast, whole-file checks. No tests, because
# pre-commit runs on every commit and the suite takes a couple of seconds.
lint: lint-ruff lint-mypy

# pyflakes, pycodestyle, isort, pyupgrade, bugbear, and the rest of the set
# configured in pyproject.toml. Fixes are NOT applied: see `just fix`.
lint-ruff:
    {{ruff}} check .

# Same idea for the type stub in stubs/. This needs no plugin's dependencies:
# the stub describes the launcher API, not the plugins.
lint-mypy:
    {{mypy}}

# --- tests ---------------------------------------------------------------------

# The whole suite, doctests included, with the internet tests left out. Those
# need a real network and fail on a 403 behind a proxy, which has nothing to do
# with the code under test - see conftest.py.
test:
    {{pytest}}

# The two suites that were written for this, on their own.
test-dockge:
    {{pytest}} plugins/dockge

test-pastebin:
    {{pytest}} plugins/pastebin

# Doctests only. These are the docstring examples in the plugin code, and they
# are the cheapest documentation regression there is: a doctest that passes is a
# usage example that is still true.
test-doctests:
    {{pytest}} --doctest-modules plugins

# Everything, including the tests that reach out to the internet. Expect the
# link-checking test in plugins/saxophone to fail behind a proxy.
test-network:
    {{pytest}} --run-network

# --- fixing --------------------------------------------------------------------

# Apply the fixes ruff considers safe, and show what is left. This rewrites
# files, so it is not part of `just lint`; run it and read the diff.
fix:
    {{ruff}} check --fix .

# The same, but including the fixes ruff calls unsafe. Those can change
# behaviour, so this one is not for a half-finished state.
fix-unsafe:
    {{ruff}} check --fix --unsafe-fixes .

# --- packaging -----------------------------------------------------------------

# Build one Debian package containing every plugin, installed under
# /usr/share/albert/python/plugins. Writes dist/albert-plugins_<version>_all.deb
# and prints its path. Needs dpkg-deb (devbox provides it).
deb:
    ./packaging/build-deb.sh

# The end-to-end check for that package: build it, install it system-wide with
# dpkg (root or passwordless sudo) and import every plugin from where it
# landed, the way the launcher does on startup. `just test` already builds,
# unpacks and imports the package; this recipe additionally performs the real
# install. Set up so it is the same smoke test, just with the install enabled.
deb-smoke:
    ALBERT_DEB_INSTALL=1 {{pytest}} test/test_deb_package.py

# --- housekeeping --------------------------------------------------------------

# The dependencies of the tooling itself, not of any plugin. Deliberately
# short: ruff, mypy, pytest and pre-commit, all of which are pure python or a
# single binary. Anything a plugin needs belongs in that plugin's
# md_lib_dependencies.
install-tools:
    {{python}} -m pip install --upgrade pip
    {{python}} -m pip install ruff mypy pytest pre-commit

# Run the hooks over the whole tree. Normally unnecessary - pre-commit runs on
# commit by itself - but this is what to run after changing .pre-commit-config.
pre-commit-all:
    {{venv}}/bin/pre-commit run --all-files
