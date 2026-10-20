# AGENTS.md

A collection of Python plugins for the [Albert](https://albertlauncher.github.io/)
launcher (python interface `5.0`). Each plugin is a directory under `plugins/`
with an `__init__.py` carrying the `md_*` metadata.

## Environment and commands

`devbox.json` provisiones the toolchain; `just` is the source of truth for
everything that runs. Enter the environment with `devbox shell`, which creates
`.venv` and installs the tools on first use. From then on, drive everything
through `just` — devbox defines no task scripts of its own.

| Command           | What it does                                                    |
| ----------------- | --------------------------------------------------------------- |
| `just`            | List the recipes.                                               |
| `just lint`       | `ruff check` + `mypy` (what pre-commit enforces).               |
| `just test`       | `pytest`, doctests included, network tests excluded.            |
| `just check`      | `lint` + `test`; run before pushing.                            |
| `just fix`        | Apply ruff's safe fixes.                                        |
| `just deb`        | Build `dist/albert-plugins_<version>_all.deb`.                  |
| `just deb-smoke`  | Build + install the .deb and import every installed plugin.     |
| `just install-tools` | Install ruff/mypy/pytest/pre-commit into `.venv`.            |

CI (`.github/workflows/`) activates the devbox environment and then calls the
same `just` recipes, so do not duplicate their logic in YAML.

## Conventions

- **Python 3.8 floor.** Ruff's `UP` rules enforce it; do not use newer syntax
  in `plugins/`. `stubs/*.pyi` is exempt.
- **Line length 95.** Enforced by ruff. There is no `black`/`ruff format` step;
  wrap lines by hand.
- **Logging.** `debug/info/warning/critical` are injected into each plugin
  module by the launcher's loader. Call them as bare globals; never
  `from albert import debug`.
- **`albert` is not importable.** `stubs/albert/__init__.pyi` satisfies mypy and
  `test/albert_stub.py` satisfies pytest. A name used from `albert` must exist in
  both, or `test/test_albert_stub.py` fails.
- **Third-party deps** belong to a plugin: declare them in its
  `md_lib_dependencies`. The launcher installs them into a per-plugin venv, so
  the repo's own `.venv` deliberately stays small.
- **Legacy plugins** carry per-file lint/type exemptions in `pyproject.toml`.
  New code is not exempt; when tidying a file, delete its exemption line.

## Tests

- Live in `plugins/<name>/test/`; import the plugin with
  `from conftest import load_plugin`.
- Anything needing the internet is marked `@pytest.mark.network` and skipped
  unless `--run-network` (`just test-network`).
- New plugins: copy `cookiecutter/` and add an entry to the root `README.md`.

## Packaging

`packaging/build-deb.sh` builds a single `albert-plugins` Debian package that
installs every plugin under `/usr/share/albert/python/plugins` (no `test/`,
`misc/` or `__pycache__`). `test/test_deb_package.py` is its smoke test: it
builds, inspects, extracts and imports each plugin the way the launcher does.
With `ALBERT_DEB_INSTALL=1` (set by `just deb-smoke`) it also does a real
`dpkg -i` using root or passwordless sudo.

## Git

- Never commit secrets or API keys.
- Commit subjects in imperative mood (see `.github/CONTRIBUTING.md`).
