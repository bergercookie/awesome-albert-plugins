"""Errno operations."""

import subprocess
import traceback
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    PluginInstance,
    StandardItem,
    setClipboardText,
)

md_iid = "5.0"
md_version = "0.3"
md_name = "Errno lookup operations"
md_description = "Lookup error codes alongside their full name and description"
md_license = "MIT"
md_url = "https://github.com/bergercookie/awesome-albert-plugins"
md_maintainers = ["Nikos Koukis"]
md_bin_dependencies = ["errno"]

ICON_PATH = Path(__file__).parent / "errno_lookup.png"


def _load_codes() -> Dict[str, Tuple[str, str]]:
    """Maps an errno name to its (code, description) pair."""
    try:
        out = subprocess.check_output(["errno", "--list"]).decode("utf-8")
    except (OSError, subprocess.SubprocessError):
        return {}
    return {li[1]: (li[0], li[2]) for li in (l.split(maxsplit=2) for l in out.splitlines()) if len(li) == 3}


# main plugin class ------------------------------------------------------------
class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        self.cache_path = Path(self.cacheLocation())
        self.config_path = Path(self.configLocation())
        self.data_path = Path(self.dataLocation())

        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=True, exist_ok=True)

        self.codes_d = _load_codes()

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "err "

    def synopsis(self, query):
        return "error number or description ..."

    def get_as_item(self, t: Tuple[str, Tuple[str, str]]) -> StandardItem:
        return StandardItem(
            id=f"errno-lookup-{t[1][0]}",
            icon_factory=self.makeIcon,
            text=f"{t[0]} - {t[1][0]}",
            subtext=f"{t[1][1]}",
            input_action_text="",
        )

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        try:
            query_str: str = ctx.query
            results = []
            for item in self.codes_d.items():
                if query_str in item[0]:
                    results.append(self.get_as_item(item))
                else:
                    for v in item[1]:
                        if query_str.lower() in v.lower():
                            results.append(self.get_as_item(item))
                            break

            yield results

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)

            yield [
                StandardItem(
                    id="errno-lookup-error",
                    icon_factory=self.makeIcon,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        Action(
                            "copy",
                            f"Copy error - report it to {md_url[8:]}",
                            lambda: setClipboardText(trace),
                        )
                    ],
                )
            ]
