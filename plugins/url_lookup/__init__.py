"""HTTP URL Lookup operations."""

import traceback
from pathlib import Path
from typing import Iterator, List, Tuple

import requests

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
md_name = "HTTP URL Lookup codes"
md_description = "HTTP URL Lookup codes and their description such as 404, 301, etc."
md_license = "MIT"
md_url = "https://github.com/bergercookie/awesome-albert-plugins"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["requests"]

ICON_PATH = Path(__file__).parent / "url_lookup.png"

codes_d = {str(k): v for k, v in requests.status_codes._codes.items()}


# supplementary functions ---------------------------------------------------------------------
def get_as_item(t: Tuple[str, tuple]) -> StandardItem:
    return StandardItem(
        id=f"url-lookup-{t[0]}",
        icon_factory=Plugin.makeIcon,
        text=f"{t[0]} - {t[1][0]}",
        subtext="",
        input_action_text="",
        actions=[
            Action("open", "More info", lambda: openUrl(f"https://httpstatuses.com/{t[0]}")),
        ],
    )


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

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "url "

    def synopsis(self, query):
        return "some url code e.g., 404"

    def save_data(self, data: str, data_name: str):
        """Save a piece of data in the configuration directory."""
        with open(self.config_path / data_name, "w") as f:
            f.write(data)

    def load_data(self, data_name) -> str:
        """Load a piece of data from the configuration directory."""
        with open(self.config_path / data_name, "r") as f:
            return f.readline().strip().split()[0]

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        results = []

        try:
            query_str = ctx.query
            for item in codes_d.items():
                if query_str in item[0]:
                    results.append(get_as_item(item))
                else:
                    # multiple descriptions per code
                    for v in item[1]:
                        if query_str in v:
                            results.append(get_as_item(item))
                            break

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)
            results.insert(
                0,
                StandardItem(
                    id="url-lookup-error",
                    icon_factory=self.makeIcon,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        Action(
                            "copy",
                            f"Copy error - report it to {md_url[8:]}",
                            lambda: setClipboardText(trace),
                        )
                    ],
                ),
            )

        yield results
