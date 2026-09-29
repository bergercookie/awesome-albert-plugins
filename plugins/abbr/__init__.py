"""User-defined abbreviations read/written a file."""

import hashlib
import traceback
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

import gi
from fuzzywuzzy import process

gi.require_version("Notify", "0.7")  # isort:skip
gi.require_version("GdkPixbuf", "2.0")  # isort:skip
from gi.repository import GdkPixbuf, Notify  # isort:skip

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
md_name = "User-defined abbreviations read/written a file"
md_description = "TODO"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/abbr"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["fuzzywuzzy"]

ICON_PATH = Path(__file__).parent / "abbr.png"

abbreviations_path = Path()
abbr_latest_hash = ""
abbr_latest_d: Dict[str, str] = {}
abbr_latest_d_bi: Dict[str, str] = {}
split_at = ":"


# plugin main functions -----------------------------------------------------------------------


def save_abbr(name: str, desc: str):
    with open(abbreviations_path, "a") as f:
        li = f"\n* {name}: {desc}"
        f.write(li)


# supplementary functions ---------------------------------------------------------------------
def notify(
    msg: str,
    app_name: str = md_name,
    image=str(ICON_PATH),
):
    Notify.init(app_name)
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def sanitize_string(s: str) -> str:
    return s.replace("<", "&lt;")


def get_as_subtext_field(field, field_title=None) -> str:
    """Get a certain variable as part of the subtext, along with a title for that variable."""
    s = ""
    if field:
        s = f"{field} | "
    else:
        return ""

    if field_title:
        s = f"{field_title}: " + s

    return s


def make_latest_dict(conts: list):
    d = {}
    for li in conts:
        tokens = li.split(split_at, maxsplit=1)
        if len(tokens) == 2:
            # avoid cases where one of the two sides is essentially empty
            if any([not t for t in tokens]):
                continue

            tokens = [t.strip().strip("*") for t in tokens]
            d[tokens[0]] = tokens[1]

    return d


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

        self.cache_path = Path(self.cacheLocation())
        self.config_path = Path(self.configLocation())
        self.data_path = Path(self.dataLocation())

        # create plugin locations
        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=True, exist_ok=True)

        self.abbr_store_fname = self.config_path / "fname"
        self.abbr_store_sep = self.config_path / "separator"

        self.load_settings()

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "ab "

    def synopsis(self, query):
        return "abbreviation to look for"

    def load_settings(self) -> None:
        """Read back the abbreviations file and the separator given in a previous run."""
        global abbreviations_path, split_at

        # abbreviations file
        if self.abbr_store_fname.is_file():
            with open(self.abbr_store_fname, "r") as f:
                p = Path(f.readline().strip()).expanduser()
                if not p.is_file():
                    raise FileNotFoundError(p)

                abbreviations_path = p

        if self.abbr_store_sep.is_file():
            with open(self.abbr_store_sep, "r") as f:
                sep = f.read(1)
                if not sep:
                    raise RuntimeError(f"Invalid separator: {sep}")

                split_at = sep

    def get_abbr_as_item(self, abbr: Tuple[str, str], key: str = "") -> StandardItem:
        """Return the abbreviation pair as an item - ready to be appended to the items list and be rendered by Albert.

        `key` is the description this item was matched on - both the abbreviation and its
        description may match the query, and only that keeps the two items' ids apart
        """
        text = abbr[0].strip()
        subtext = abbr[1].strip()

        return StandardItem(
            id=f"abbr-{text}-{key}" if key else f"abbr-{text}",
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

    def submit_fname(self, p: Path):
        p = p.expanduser().resolve()
        if p.is_file():
            with open(self.abbr_store_fname, "w") as f:
                f.write(str(p))

            global abbreviations_path
            abbreviations_path = p
        else:
            notify(f"Given file path does not exist -> {p}")

    def submit_sep(self, c: str):
        if len(c) > 1:
            notify("Separator must be a single character!")
            return

        with open(self.abbr_store_sep, "w") as f:
            f.write(c)

        global split_at
        split_at = c

    def setup(self, ctx) -> List[StandardItem]:
        """Setup is successful if an empty list is returned.

        Use this function if you need the user to provide you data
        """

        query_str = ctx.query

        # abbreviations file
        if not self.abbr_store_fname.is_file():
            return [
                StandardItem(
                    id="abbr-setup-fname",
                    icon_factory=self.makeIcon,
                    text="Specify file to read/write abbreviations to/from",
                    subtext="Paste the path to the file, then press ENTER",
                    actions=[
                        Action(
                            "submit",
                            "Submit path",
                            lambda p=query_str: self.submit_fname(Path(p)),
                        ),
                    ],
                )
            ]

        if not self.abbr_store_sep.is_file():
            return [
                StandardItem(
                    id="abbr-setup-separator",
                    icon_factory=self.makeIcon,
                    text="Specify separator *character* for abbreviations",
                    subtext=f"Separator: {query_str}",
                    actions=[
                        Action(
                            "submit",
                            "Submit separator",
                            lambda c=query_str: self.submit_sep(c),
                        ),
                    ],
                )
            ]

        return []

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        """Called by albert with *every new keypress*."""
        try:
            results_setup = self.setup(ctx)
            if results_setup:
                yield results_setup
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

            # new behavior
            tokens = query_str.split()
            if len(tokens) >= 1 and tokens[0] == "new":
                if len(tokens) > 1:
                    name = tokens[1]
                else:
                    name = ""
                if len(tokens) > 2:
                    desc = " ".join(tokens[2:])
                else:
                    desc = ""

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
                                lambda name=name, desc=desc: save_abbr(name, desc),
                            )
                        ],
                    )
                ]

                return

            curr_hash = hash_file(abbreviations_path)
            global abbr_latest_hash, abbr_latest_d, abbr_latest_d_bi
            if abbr_latest_hash != curr_hash:
                abbr_latest_hash = curr_hash
                with open(abbreviations_path) as f:
                    conts = f.readlines()
                    abbr_latest_d = make_latest_dict(conts)
                    abbr_latest_d_bi = abbr_latest_d.copy()
                    abbr_latest_d_bi.update({v: k for k, v in abbr_latest_d.items()})

            if not abbr_latest_d:
                yield [
                    StandardItem(
                        id="abbr-no-entries",
                        icon_factory=self.makeIcon,
                        text=f'No lines split by "{split_at}" in the file provided',
                        actions=[
                            Action(
                                "copy",
                                "Copy provided filename",
                                lambda t=str(abbreviations_path): setClipboardText(t),
                            )
                        ],
                    )
                ]

                return

            # do fuzzy search on both the abbreviations and their description
            results = []
            matched = process.extract(query_str, abbr_latest_d_bi.keys(), limit=10)
            for m in [elem[0] for elem in matched]:
                if m in abbr_latest_d.keys():
                    results.append(self.get_abbr_as_item((m, abbr_latest_d[m])))
                else:
                    results.append(self.get_abbr_as_item((abbr_latest_d_bi[m], m), m))

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
