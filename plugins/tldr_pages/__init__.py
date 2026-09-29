"""TL;DR pages from albert."""

import re
import subprocess
import traceback
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

from fuzzywuzzy import process

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
md_name = "TL;DR pages from albert."
md_description = "View tldr pages from inside albert"
md_url = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins//tldr_pages"
)
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["fuzzywuzzy"]

md_bin_dependencies = ["git"]
ICON_PATH = Path(__file__).parent / "tldr_pages.png"

# Is the plugin run in development mode?
in_development = False

# supplementary functions ---------------------------------------------------------------------


def sanitize_string(s: str) -> str:
    return s.replace("<", "&lt;")


def get_cmd_sanitized(s: str) -> str:
    return sanitize_string(s.strip("`").replace("{{", "").replace("}}", ""))


# main plugin class ------------------------------------------------------------
class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        self.cache_path = Path(self.cacheLocation()) / "tldr_pages"
        self.config_path = Path(self.configLocation()) / "tldr_pages"
        self.data_path = Path(self.dataLocation()) / "tldr_pages"

        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=True, exist_ok=True)

        self.tldr_root = self.cache_path / "tldr"
        self.pages_root = self.tldr_root / "pages"

        self.page_paths: Dict[str, Path] = {}

        self.ensure_tldr_db()

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "tldr "

    def synopsis(self, query):
        return "some command"

    # -- tldr database ------------------------------------------------------------------------

    def ensure_tldr_db(self):
        if not self.pages_root.is_dir():
            try:
                subprocess.check_call(
                    f"git clone https://github.com/tldr-pages/tldr {self.tldr_root}".split()
                )
            except (OSError, subprocess.SubprocessError) as e:
                # No "git" binary or no network - don't fail the plugin load, the user can
                # retry from the "Update tldr database" item.
                print(f"Could not clone the tldr pages repository: {e}")
                return

        self.reindex_tldr_pages()

    def reindex_tldr_pages(self):
        self.page_paths = self.get_page_paths()

    def update_tldr_db(self):
        subprocess.check_call(f"git -C {self.tldr_root} pull --rebase origin main".split())
        self.reindex_tldr_pages()

    def get_page_paths(self) -> Dict[str, Path]:
        paths = list(self.pages_root.rglob("*.md"))

        return {p.stem: p for p in paths}

    def save_data(self, data: str, data_name: str):
        """Save a piece of data in the configuration directory."""
        with open(self.config_path / data_name, "w") as f:
            f.write(data)

    def load_data(self, data_name) -> str:
        """Load a piece of data from the configuration directory."""
        with open(self.config_path / data_name, "r") as f:
            data = f.readline().strip().split()[0]

        return data

    # -- items --------------------------------------------------------------------------------

    def get_error_item(self, trace: str) -> StandardItem:
        return StandardItem(
            id=f"{self.id()}.error",
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

    def get_cmd_as_item(self, ctx, pair: Tuple[str, Path]) -> StandardItem:
        with open(pair[-1], "r") as f:
            all_lines = f.readlines()
            description_lines = [
                li.lstrip("> ").rstrip().rstrip(".") for li in all_lines if li.startswith("> ")
            ]

            # see if there's a line with more information and a URL
            more_info_url = None
            try:
                more_info = [li for li in all_lines if "more information" in li.lower()][0]
                more_info_url = re.search("<(.*)>", more_info)
                if more_info_url is not None and more_info_url.groups():
                    more_info_url = more_info_url.groups()[0]
            except IndexError:
                pass

        actions = [
            Action("copy", "Copy command", lambda cmd=pair[0]: setClipboardText(cmd)),
            Action(
                "google",
                "Do a google search",
                lambda cmd=pair[0]: openUrl(f'https://www.google.com/search?q="{cmd}" command'),
            ),
        ]
        if more_info_url:
            actions.append(Action("open", "More information", lambda u=more_info_url: openUrl(u)))

        return StandardItem(
            id=f"{self.id()}.page-{pair[0]}",
            icon_factory=self.makeIcon,
            text=pair[0],
            input_action_text=" ".join([ctx.trigger, pair[0]]),
            subtext=" ".join(description_lines),
            actions=actions,
        )

    def get_cmd_items(self, pair: Tuple[str, Path]) -> List[StandardItem]:
        """Return a list of Albert items - one per example."""

        with open(pair[-1], "r") as f:
            lines = [li.strip() for li in f.readlines()]

        items: List[StandardItem] = []
        i = 0
        example_idx = 0
        if len(lines) < 2:
            return items

        while i < len(lines):
            li = lines[i]
            if not li.startswith("- "):
                i += 1
                continue

            desc = li.lstrip("- ")[:-1]

            # Support multine commands ------------------------------------------------------------
            #
            # find the start of the example - parse it differently if it's a single quote or if
            # it's a multiline one
            i += 2
            example_line_start = lines[i]
            if example_line_start.startswith("```"):
                # multi-line string, find end
                j = i + 1
                while j < len(lines) and lines[j] != "```":
                    j += 1
                    continue

                example_cmd = get_cmd_sanitized("\n".join(lines[i + 1 : j]))
                i = j
            else:
                example_cmd = get_cmd_sanitized(lines[i])

            items.append(
                StandardItem(
                    id=f"{self.id()}.example-{pair[0]}-{example_idx}",
                    icon_factory=self.makeIcon,
                    text=example_cmd,
                    subtext=desc,
                    actions=[
                        Action("copy", "Copy command", lambda cmd=example_cmd: setClipboardText(cmd)),
                        Action(
                            "google",
                            "Do a google search",
                            lambda cmd=pair[0]: openUrl(
                                f'https://www.google.com/search?q="{cmd}" command'
                            ),
                        ),
                    ],
                )
            )

            example_idx += 1
            i += 1

        return items

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        """Hook that is called by albert with *every new keypress*."""  # noqa
        results = []
        try:
            query_text = ctx.query.strip()

            if not len(query_text):
                results = [
                    StandardItem(
                        id=f"{self.id()}.update-db",
                        icon_factory=self.makeIcon,
                        text="Update tldr database",
                        actions=[Action("update", "Update", lambda: self.update_tldr_db())],
                    ),
                    StandardItem(
                        id=f"{self.id()}.reindex-db",
                        icon_factory=self.makeIcon,
                        text="Reindex tldr pages",
                        actions=[
                            Action("reindex", "Reindex", lambda: self.reindex_tldr_pages())
                        ],
                    ),
                    StandardItem(
                        id=f"{self.id()}.need-letters",
                        icon_factory=self.makeIcon,
                        text="Need at least 1 letter to offer suggestions",
                        actions=[],
                    ),
                ]

                yield results
                return

            if query_text in self.page_paths.keys():
                # exact match - show examples
                results.extend(self.get_cmd_items((query_text, self.page_paths[query_text])))
            else:
                # fuzzy search based on word
                matched = process.extract(query_text, self.page_paths.keys(), limit=20)

                for m in [elem[0] for elem in matched]:
                    results.append(self.get_cmd_as_item(ctx, (m, self.page_paths[m])))

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)
            if in_development:
                raise

            results.insert(0, self.get_error_item(trace))

        yield results
