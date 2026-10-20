"""Debian package smoke test: build it, install it, import the plugins back.

`packaging/build-deb.sh` turns every plugin under `plugins/` into a single
`.deb` that installs them under ``/usr/share/albert/python/plugins``, the
system-wide directory the Albert python plugin loader scans. Nothing else in
the suite looks at that package, so a plugin that only works from the source
tree, a file left out of the payload, or a byte-code cache shipped by mistake
would go unnoticed until someone installed it.

This builds the package, inspects what went in, unpacks it, and imports every
plugin from the unpacked tree the way the launcher does. With
``ALBERT_DEB_INSTALL=1`` -- set by ``just deb-smoke`` and by CI -- it goes the
whole way and ``dpkg -i``'s the package into the real filesystem first, then
imports the plugins from where they were installed.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import load_plugin_from

REPO_ROOT = Path(__file__).parent.parent
BUILD_SCRIPT = REPO_ROOT / "packaging" / "build-deb.sh"
PLUGINS_DIR = REPO_ROOT / "plugins"

PACKAGE = "albert-plugins"
#: Where build-deb.sh places the plugins, relative to the package root and to
#: `/` once installed.
INSTALL_SUBDIR = Path("usr/share/albert/python/plugins")
INSTALL_ROOT = Path("/") / INSTALL_SUBDIR

#: `just deb-smoke` sets this; it is what turns on a real `dpkg -i`.
WANT_INSTALL = os.environ.get("ALBERT_DEB_INSTALL") == "1"

pytestmark = pytest.mark.skipif(
    shutil.which("dpkg-deb") is None or shutil.which("bash") is None,
    reason="needs dpkg-deb and bash to build and inspect the package",
)


def plugin_names():
    """The plugins this repo ships, by directory name."""
    return sorted(p.parent.name for p in PLUGINS_DIR.glob("*/__init__.py"))


def import_plugins(plugin_root):
    """Import every shipped plugin from *plugin_root* as the launcher would.

    A plugin module that raises on import is a plugin Albert cannot load, so an
    exception here is a failure, not something to swallow. The v5.0 metadata is
    also checked: a module without `md_iid` is not something the loader accepts.
    """
    loaded = []
    for name in plugin_names():
        init = plugin_root / name / "__init__.py"
        assert init.is_file(), f"{name} is missing from {plugin_root}"
        module = load_plugin_from(init, name)
        assert getattr(module, "md_iid", None) == "5.0", f"{name}: bad md_iid"
        assert getattr(module, "md_name", None), f"{name}: missing md_name"
        loaded.append(name)
    return loaded


def run(command, **kwargs):
    return subprocess.run(command, capture_output=True, text=True, **kwargs)


@pytest.fixture(scope="session")
def deb(tmp_path_factory):
    """Build the package once and return the path to the .deb."""
    out_dir = tmp_path_factory.mktemp("deb-out")
    # VERSION is pinned so the filename and the metadata are deterministic and
    # do not depend on the checkout's git state.
    env = {**os.environ, "OUT_DIR": str(out_dir), "VERSION": "0.0.0+test"}
    proc = run(["bash", str(BUILD_SCRIPT)], env=env)
    assert proc.returncode == 0, f"build-deb.sh failed:\n{proc.stdout}\n{proc.stderr}"

    built = list(out_dir.glob("*.deb"))
    assert len(built) == 1, f"expected exactly one .deb, got {built}"
    return built[0]


def test_deb_metadata(deb):
    proc = run(["dpkg-deb", "-f", str(deb), "Package", "Version", "Architecture"])
    assert proc.returncode == 0, proc.stderr
    fields = dict(line.split(": ", 1) for line in proc.stdout.splitlines())
    assert fields["Package"] == PACKAGE
    assert fields["Version"] == "0.0.0+test"
    assert fields["Architecture"] == "all"


def test_deb_contains_every_plugin(deb):
    proc = run(["dpkg-deb", "-c", str(deb)])
    assert proc.returncode == 0, proc.stderr
    contents = proc.stdout

    for name in plugin_names():
        entry = f"./{INSTALL_SUBDIR}/{name}/__init__.py"
        assert entry in contents, f"{entry} is not in the package"

    # Development-only trees must not be shipped.
    assert "__pycache__" not in contents
    assert "/test/" not in contents
    assert "/misc/" not in contents


def test_deb_extracts_to_the_expected_tree(deb, tmp_path):
    root = tmp_path / "root"
    proc = run(["dpkg-deb", "-x", str(deb), str(root)])
    assert proc.returncode == 0, proc.stderr

    for name in plugin_names():
        assert (root / INSTALL_SUBDIR / name / "__init__.py").is_file()


def test_plugins_import_from_the_extracted_package(deb, tmp_path):
    root = tmp_path / "root"
    assert run(["dpkg-deb", "-x", str(deb), str(root)]).returncode == 0

    loaded = import_plugins(root / INSTALL_SUBDIR)
    assert loaded == plugin_names()


def _root_prefix():
    """``[]`` as root, ``["sudo"]`` when passwordless sudo is available, else None."""
    if os.geteuid() == 0:
        return []
    if shutil.which("sudo") and run(["sudo", "-n", "true"]).returncode == 0:
        return ["sudo"]
    return None


@pytest.mark.skipif(
    not WANT_INSTALL,
    reason="set ALBERT_DEB_INSTALL=1 (just deb-smoke) to install system-wide",
)
def test_deb_installs_and_plugins_import_system_wide(deb):
    prefix = _root_prefix()
    if prefix is None:
        pytest.skip("need root or passwordless sudo to run dpkg -i")

    dpkg = [*prefix, "dpkg"]
    install = run([*dpkg, "-i", str(deb)])
    assert install.returncode == 0, install.stderr or install.stdout
    try:
        listed = run([*dpkg, "-L", PACKAGE]).stdout
        for name in plugin_names():
            path = INSTALL_ROOT / name / "__init__.py"
            assert str(path) in listed, f"{path} was not installed"
            assert path.is_file()

        # The real check: load them from the installed (root-owned, read-only
        # for us) location exactly as Albert will on startup.
        loaded = import_plugins(INSTALL_ROOT)
        assert loaded == plugin_names()
    finally:
        # Do not leave the machine changed, and do not let a stale install make
        # the next run's dpkg -i refuse.
        run([*dpkg, "-r", PACKAGE])
        run([*dpkg, "-P", PACKAGE])
