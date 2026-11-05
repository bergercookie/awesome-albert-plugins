"""User-defined abbreviations read/written a file."""

import hashlib
import traceback
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    Notification,
    PluginInstance,
    StandardItem,
    openUrl,
    setClipboardText,
)
from fuzzywuzzy import process

md_iid = "5.0"
md_version = "0.4"
md_name = "User-defined abbreviations read/written a file"
md_description = "Store and look up abbreviations in a plain-text file"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/abbr"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["fuzzywuzzy"]

ICON_PATH = Path(__file__).parent / "abbr.png"

CONFIG_ABBREVIATIONS_PATH = "abbreviations_path"
CONFIG_SEPARATOR = "separator"
DEFAULT_SEPARATOR = ":"
LEGACY_FNAME = "fname"
LEGACY_SEPARATOR = "separator"


# plugin main functions -----------------------------------------------------------------------


def append_abbreviation(
    path: Path, name: str, desc: str, separator: str = DEFAULT_SEPARATOR
) -> None:
    with open(path, "a") as f:
        f.write(f"\n* {name}{separator} {desc}")


# supplementary functions ---------------------------------------------------------------------
def notify(
    msg: str,
    app_name: str = md_name,
):
    Notification(app_name, msg).send()


def make_latest_entries(
    conts: list, separator: str = DEFAULT_SEPARATOR
) -> List[Tuple[str, str]]:
    entries = []
    for li in conts:
        tokens = li.split(separator, maxsplit=1)
        if len(tokens) == 2:
            # avoid cases where one of the two sides is essentially empty
            if any(not t for t in tokens):
                continue

            tokens = [t.strip().strip("*").strip() for t in tokens]
            entries.append((tokens[0], tokens[1]))

    return entries


def make_search_index(entries: List[Tuple[str, str]]) -> Dict[str, List[int]]:
    """Map every abbreviation and description to the entries that contain it."""
    index: Dict[str, List[int]] = {}
    for i, entry in enumerate(entries):
        for term in entry:
            index.setdefault(term, []).append(i)

    return index


def hash_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p) as f:
        h.update(f.read().encode("utf-8"))
        return h.hexdigest()


# main plugin class ------------------------------------------------------------
class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        self._migrate_legacy_settings()

        configured_path = str(self.readConfig(CONFIG_ABBREVIATIONS_PATH, str) or "").strip()
        self._abbreviations_path: Optional[Path] = (
            Path(configured_path).expanduser() if configured_path else None
        )

        configured_separator = str(self.readConfig(CONFIG_SEPARATOR, str) or "")
        self._separator: str = configured_separator or DEFAULT_SEPARATOR

        self._latest_hash: str = ""
        self._entries: List[Tuple[str, str]] = []
        self._search: Dict[str, List[int]] = {}

    def _migrate_legacy_settings(self) -> None:
        """Read the file-based settings of older releases once, then forget them."""
        config_path = Path(self.configLocation())

        legacy_fname = config_path / LEGACY_FNAME
        if not self.readConfig(CONFIG_ABBREVIATIONS_PATH, str) and legacy_fname.is_file():
            value = legacy_fname.read_text().strip()
            if value:
                self.writeConfig(CONFIG_ABBREVIATIONS_PATH, value)

        legacy_separator = config_path / LEGACY_SEPARATOR
        if not self.readConfig(CONFIG_SEPARATOR, str) and legacy_separator.is_file():
            value = legacy_separator.read_text()[:1]
            if value:
                self.writeConfig(CONFIG_SEPARATOR, value)

    # -- config, bound to the settings widget below ---------------------------------------

    @property
    def abbreviations_path(self) -> str:
        return "" if self._abbreviations_path is None else str(self._abbreviations_path)

    @abbreviations_path.setter
    def abbreviations_path(self, value: str):
        value = (value or "").strip()
        self.writeConfig(CONFIG_ABBREVIATIONS_PATH, value)
        self._abbreviations_path = Path(value).expanduser() if value else None
        self._forget()

    @property
    def separator(self) -> str:
        return self._separator

    @separator.setter
    def separator(self, value: str):
        value = (value or "").strip()
        if len(value) > 1:
            notify("Separator must be a single character!")
            return

        self._separator = value or DEFAULT_SEPARATOR
        self.writeConfig(CONFIG_SEPARATOR, self._separator)
        self._forget()

    def configWidget(self):
        return [
            {
                "type": "label",
                "text": (
                    "Path to the file holding the abbreviations. Each line is read as "
                    "'* abbreviation: description', and new abbreviations are appended to it."
                ),
            },
            {
                "type": "lineedit",
                "property": "abbreviations_path",
                "label": "Abbreviations file",
                "widget_properties": {"placeholderText": "/home/you/abbreviations.txt"},
            },
            {
                "type": "label",
                "text": "The character that separates an abbreviation from its description.",
            },
            {
                "type": "lineedit",
                "property": "separator",
                "label": "Separator",
                "widget_properties": {"placeholderText": ":", "maxLength": 1},
            },
        ]

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "ab "

    def synopsis(self, query):
        return "abbreviation to look for"

    # -- abbreviations file -----------------------------------------------------------------

    def _forget(self) -> None:
        self._latest_hash = ""
        self._entries = []
        self._search = {}

    def _reload(self) -> None:
        path = self._abbreviations_path
        if path is None:
            return

        curr_hash = hash_file(path)
        if curr_hash == self._latest_hash:
            return

        with open(path) as f:
            conts = f.readlines()

        self._entries = make_latest_entries(conts, self._separator)
        self._search = make_search_index(self._entries)
        self._latest_hash = curr_hash

    def save_abbr(self, name: str, desc: str) -> None:
        path = self._abbreviations_path
        if path is None:
            notify("No abbreviations file is configured.")
            return

        append_abbreviation(path, name, desc, self._separator)
        self._forget()

    # -- items --------------------------------------------------------------------------------

    def _setup_item(self) -> Optional[StandardItem]:
        if self._abbreviations_path is None:
            return StandardItem(
                id="abbr-setup-fname",
                icon_factory=self.makeIcon,
                text="Please fill in the plugin settings - abbreviations file missing",
                subtext=(
                    "Open the Abbreviations plugin in the Albert settings to configure it."
                ),
            )

        if not self._abbreviations_path.is_file():
            return StandardItem(
                id="abbr-setup-fname-missing",
                icon_factory=self.makeIcon,
                text=f"Abbreviations file not found: {self._abbreviations_path}",
                subtext="Fix the path in the plugin settings.",
                actions=[
                    Action(
                        "copy",
                        "Copy the configured path",
                        lambda t=str(self._abbreviations_path): setClipboardText(t),
                    )
                ],
            )

        return None

    def get_abbr_as_item(self, abbr: Tuple[str, str], suffix: str = "") -> StandardItem:
        """Return the abbreviation pair as an item ready for Albert.

        `suffix` keeps items with the same abbreviation and description apart.
        """
        text = abbr[0].strip()
        subtext = abbr[1].strip()

        return StandardItem(
            id=f"abbr-{text}-{suffix}" if suffix else f"abbr-{text}",
            icon_factory=self.makeIcon,
            text=f"{text}",
            subtext=f"{subtext}",
            actions=[
                Action(
                    "open",
                    "Open in Google",
                    lambda u=f"https://www.google.com/search?&q={text}": openUrl(u),
                ),
                Action("copy", "Copy abbreviation", lambda t=text: setClipboardText(t)),
                Action("copy", "Copy description", lambda t=subtext: setClipboardText(t)),
            ],
        )

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        """Called by albert with *every new keypress*."""
        try:
            setup = self._setup_item()
            if setup is not None:
                yield [setup]
                return

            query_str = ctx.query

            if len(query_str.strip().split()) == 0:
                yield [
                    StandardItem(
                        id="abbr-hint-new",
                        icon_factory=self.makeIcon,
                        text="[new] Add a new abbreviation",
                        subtext="new <u>abbreviation</u> <u>description</u>",
                        input_action_text=f"{ctx.trigger} new ",
                    ),
                    StandardItem(
                        id="abbr-hint-query",
                        icon_factory=self.makeIcon,
                        text="Write more to query the database",
                        subtext="",
                        input_action_text=ctx.trigger,
                    ),
                ]

                return

            tokens = query_str.split()
            if len(tokens) >= 1 and tokens[0] == "new":
                name = tokens[1] if len(tokens) > 1 else ""
                desc = " ".join(tokens[2:]) if len(tokens) > 2 else ""

                yield [
                    StandardItem(
                        id=f"abbr-new-{name}",
                        icon_factory=self.makeIcon,
                        text=f"New abbreviation: {name}",
                        subtext=f"Description: {desc}",
                        actions=[
                            Action(
                                "save",
                                "Save abbreviation to file",
                                lambda name=name, desc=desc: self.save_abbr(name, desc),
                            )
                        ],
                    )
                ]

                return

            self._reload()

            if not self._entries:
                yield [
                    StandardItem(
                        id="abbr-no-entries",
                        icon_factory=self.makeIcon,
                        text=f'No lines split by "{self._separator}" in the file provided',
                        actions=[
                            Action(
                                "copy",
                                "Copy provided filename",
                                lambda t=str(self._abbreviations_path): setClipboardText(t),
                            )
                        ],
                    )
                ]

                return

            # do fuzzy search on both the abbreviations and their descriptions
            results = []
            seen = set()
            matched = process.extract(query_str, self._search.keys(), limit=10)
            for term in [elem[0] for elem in matched]:
                for i in self._search[term]:
                    if i in seen:
                        continue

                    seen.add(i)
                    results.append(self.get_abbr_as_item(self._entries[i], str(i)))

            yield results

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)

            yield [
                StandardItem(
                    id="abbr-error",
                    icon_factory=self.makeIcon,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        Action(
                            "copy",
                            f"Copy error - report it to {md_url[8:]}",
                            lambda t=trace: setClipboardText(t),
                        )
                    ],
                )
            ]
