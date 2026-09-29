# Porting a plugin to the Albert Python 5.0 interface

Target: `md_iid = "5.0"`. Reference implementation: any migrated plugin under
`plugins/` (e.g. `plugins/errno_lookup/__init__.py`).

The old API exposed one big `v0` module, a `QueryHandler` base class, and a
`handleQuery()` callback. The new one is explicit imports, a composed base
class, and a generator.

## Skeleton

```python
from pathlib import Path
from typing import Iterator, List

from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    PluginInstance,
    StandardItem,
    openUrl,
    setClipboardText,
)

md_iid = "5.0"
md_version = "0.3"
md_name = "My Plugin"
md_description = "..."
md_license = "MIT"
md_url = "https://github.com/bergercookie/awesome-albert-plugins"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = []
md_bin_dependencies = []

ICON_PATH = Path(__file__).parent / "my_plugin.svg"


class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        self.cache_path = Path(self.cacheLocation())
        self.config_path = Path(self.configLocation())
        self.data_path = Path(self.dataLocation())
        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "m "

    def synopsis(self, query):
        return "description of what to type"

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        yield [StandardItem(id="my-plugin.greeting", icon_factory=self.makeIcon,
                            text="Hello", actions=[])]
```

## Steps

1. **Imports.** Drop `import albert as v0`; import the names you use from
   `albert`. `debug` / `info` / `warning` / `critical` are *not* importable —
   the loader injects them into the plugin module, so just call them.

2. **Metadata.** `md_iid` must be exactly `"5.0"`. `md_authors` and
   `md_maintainers` must be **lists**, not strings. Drop `md_id`,
   `__iid__`, `__prettyname__`, `__version__`, `__trigger__`, `__author__`.
   Keep the existing name, description and maintainer.

   `md_lib_dependencies` must list **PyPI distribution names**, not import
   names — Albert compares each entry against `pip freeze` and `pip install`s
   whatever is missing. So `import netifaces` → `"netifaces"`, but
   `import PIL` → `"Pillow"`, `import dateutil` → `"python-dateutil"`,
   `import bs4` → `"beautifulsoup4"`, `import em` → `"em-keyboard"`. Do not
   pin versions (`"tzlocal==2.1"`) or add extras (`"thefuzz[speedup]"`) — the
   name is compared literally, so a pin never matches and triggers a reinstall
   on every load. Do **not** declare stdlib modules, and do **not** declare
   `gi`: PyGObject is a system package, and the `gi` name on PyPI is an
   unrelated project. Put those install hints in the plugin README instead.

3. **Paths.** `v0.cacheLocation()` etc. no longer exist. Call the instance
   methods in `__init__` and create the directories yourself — `parents=True`,
   since the app-data parent may not exist yet.

4. **Base class.** `v0.QueryHandler` → `PluginInstance, GeneratorQueryHandler`,
   with both `__init__`s called. Delete `id()`, `name()` and `description()`;
   they are inherited. Fold `initialize()` into `__init__` and drop
   `finalize()` (use `__del__` if you really need one). `synopsis()` now takes
   the query.

5. **`handleQuery()` → `items()`.** Make it a generator that yields **lists**:

   | old | new |
   | --- | --- |
   | `query.string` | `ctx.query` |
   | `query.add(items)` | `yield items` |
   | `return items` | `yield items` |
   | `return` | `return` |

   Yielding a bare item instead of a list is a runtime error. In long loops
   bail out with `if not ctx.isValid: return` so stale queries stop early.

6. **Items.** `v0.Item(...)` → `StandardItem(...)`, with three renames:
   `completion=` → `input_action_text=`, `icon=[path]` →
   `icon_factory=self.makeIcon`, and **`id` must now be unique per item**. Old
   code often used `id=md_name` everywhere, which collapses distinct results
   during ranking — derive a stable key instead (`f"errno-lookup-{code}"`,
   `f"contacts-{email}"`, `f"task-{uuid}"`).

   `icon_factory` is a zero-arg callable: pass the reference, never its result.
   Icons load lazily, so a wrong path only fails when the item is rendered —
   make sure it points at a file that exists.

7. **Actions.** Delete the `UrlAction` / `ClipAction` / `FuncAction` shims and
   pass all three arguments positionally to `Action`:

   ```python
   Action("open", "Open in browser", lambda: openUrl(url))
   Action("copy", "Copy UUID", lambda: setClipboardText(text))
   Action("run", "Reload", self.reload)
   ```

   Capture eagerly inside the lambda. Bind anything that must survive the
   current scope as a default arg (`lambda u=url: ...`), and never build an
   `Action` that reads a traceback from a live `except` block — format it into a
   local first.

8. **Renames.**

   | old | new |
   | --- | --- |
   | `v0.openUrl` / `v0.openFile` | `openUrl` / `openFile` |
   | `v0.setClipboardText` | `setClipboardText` |
   | `v0.runProcess([...])` | `runDetachedProcess([...])` (does not capture output) |
   | `v0.critical(...)` | `critical(...)` (injected) |
   | `v0.util.fuzzy_match` | `Matcher` / `Match` / `MatchConfig` |
   | `v0.Hook`, `v0.fzf`, `hideWindow()` | removed |

## House style

`black` / `isort`, **line length 95** (see `pyproject.toml`). Keep
`typing.List` / `typing.Dict` rather than builtin generics so the Python 3.8
target still holds. Preserve the plugin's existing docstrings, comments and
helper structure — this is an API port, not a rewrite.

## Verify

```sh
python3 -m compileall -q plugins/<name>
rg 'v0\.|handleQuery|completion=|md_iid = "0' plugins/<name>/__init__.py
```

The second command should return nothing. Then enable the plugin in Albert and
type its trigger with and without a query string — a plugin that only ever
yields under a non-empty query is a common porting mistake.
