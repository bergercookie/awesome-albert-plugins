"""User-defined abbreviations read/written a file."""

import hashlib
import traceback
from pathlib import Path
from typing import Dict, Tuple

import gi
from fuzzywuzzy import process

gi.require_version("Notify", "0.7")  # isort:skip
gi.require_version("GdkPixbuf", "2.0")  # isort:skip
from gi.repository import GdkPixbuf, Notify  # isort:skip

import albert as v0

md_name = "User-defined abbreviations read/written a file"
md_description = "TODO"
md_iid = "0.5"
md_version = "0.5"
md_maintainers = "Nikos Koukis"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/abbr"

icon_path = str(Path(__file__).parent / "abbr")

cache_path = Path(v0.cacheLocation()) / "abbr"
config_path = Path(v0.configLocation()) / "abbr"
data_path = Path(v0.dataLocation()) / "abbr"
dev_mode = True

abbr_store_fname = config_path / "fname"
abbr_store_sep = config_path / "separator"
abbreviations_path = Path()
abbr_latest_hash = ""
abbr_latest_d: Dict[str, str] = {}
abbr_latest_d_bi: Dict[str, str] = {}
split_at = ":"

# plugin main functions -----------------------------------------------------------------------

if abbr_store_fname.is_file():
    with open(abbr_store_fname, "r") as f:
        p = Path(f.readline().strip()).expanduser()
        if not p.is_file():
            raise FileNotFoundError(p)

        abbreviations_path = p

if abbr_store_sep.is_file():
    with open(abbr_store_sep, "r") as f:
        sep = f.read(1)
        if not sep:
            raise RuntimeError(f"Invalid separator: {sep}")

        split_at = sep


def save_abbr(name: str, desc: str):
    with open(abbreviations_path, "a") as f:
        li = f"\n* {name}: {desc}"
        f.write(li)


# supplementary functions ---------------------------------------------------------------------
def notify(
    msg: str,
    app_name: str = md_name,
    image=str(icon_path),
):
    Notify.init(app_name)
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def get_abbr_as_item(abbr: Tuple[str, str]):
    """Return the abbreviation pair as an item - ready to be appended to the items list and be rendered by Albert."""
    text = abbr[0].strip()
    subtext = abbr[1].strip()

    return v0.Item(
        id=md_name,
        icon=[icon_path],
        text=f"{text}",
        subtext=f"{subtext}",
        actions=[
            UrlAction("Open in Google", f"https://www.google.com/search?&q={text}"),
            ClipAction("Copy abbreviation", text),
            ClipAction("Copy description", subtext),
        ],
    )


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


def submit_fname(p: Path):
    p = p.expanduser().resolve()
    if p.is_file():
        with open(abbr_store_fname, "w") as f:
            f.write(str(p))

        global abbreviations_path
        abbreviations_path = p
    else:
        notify(f"Given file path does not exist -> {p}")


def submit_sep(c: str):
    if len(c) > 1:
        notify("Separator must be a single character!")
        return

    with open(abbr_store_sep, "w") as f:
        f.write(c)

    global split_at
    split_at = c


def setup(query) -> bool:
    """Setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    query_str = query.string

    # abbreviations file
    if not abbr_store_fname.is_file():
        query.add(
            v0.Item(
                id=md_name,
                icon=[icon_path],
                text="Specify file to read/write abbreviations to/from",
                subtext="Paste the path to the file, then press ENTER",
                actions=[
                    FuncAction("Submit path", lambda p=query_str: submit_fname(Path(p))),
                ],
            )
        )
        return True

    if not abbr_store_sep.is_file():
        query.add(
            v0.Item(
                id=md_name,
                icon=[icon_path],
                text="Specify separator *character* for abbreviations",
                subtext=f"Separator: {query_str}",
                actions=[
                    FuncAction("Submit separator", lambda c=query_str: submit_sep(c)),
                ],
            )
        )
        return True

    return False


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


# helpers for backwards compatibility ------------------------------------------
class UrlAction(v0.Action):
    def __init__(self, name: str, url: str):
        super().__init__(name, name, lambda: v0.openUrl(url))


class ClipAction(v0.Action):
    def __init__(self, name, copy_text):
        super().__init__(name, name, lambda: v0.setClipboardText(copy_text))


class FuncAction(v0.Action):
    def __init__(self, name, command):
        super().__init__(name, name, command)


# main plugin class ------------------------------------------------------------
class Plugin(v0.QueryHandler):
    def id(self) -> str:
        return __name__

    def name(self) -> str:
        return md_name

    def description(self):
        return md_description

    def defaultTrigger(self):
        return "ab "

    def synopsis(self):
        return "abbreviation to look for"

    def initialize(self):
        """Called when the extension is loaded (ticked in the settings) - blocking."""

        # create plugin locations
        for p in (cache_path, config_path, data_path):
            p.mkdir(parents=False, exist_ok=True)

    def finalize(self):
        pass

    def handleQuery(self, query):
        """Hook that is called by albert with *every new keypress*."""  # noqa
        try:
            results_setup = setup(query)
            if results_setup:
                return

            query_str = query.string

            if len(query_str.strip().split()) == 0:
                query.add(
                    v0.Item(
                        id=md_name,
                        icon=[icon_path],
                        text="[new] Add a new abbreviation",
                        subtext="new <u>abbreviation</u> <u>description</u>",
                        completion=f"{query.trigger} new ",
                    )
                )
                query.add(
                    v0.Item(
                        id=md_name,
                        icon=[icon_path],
                        text="Write more to query the database",
                        subtext="",
                        completion=query.trigger,
                    )
                )

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

                query.add(
                    v0.Item(
                        id=md_name,
                        icon=[icon_path],
                        text=f"New abbreviation: {name}",
                        subtext=f"Description: {desc}",
                        actions=[
                            FuncAction(
                                "Save abbreviation to file",
                                lambda name=name, desc=desc: save_abbr(name, desc),
                            )
                        ],
                    )
                )

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
                query.add(
                    v0.Item(
                        id=md_name,
                        icon=[icon_path],
                        text=f'No lines split by "{split_at}" in the file provided',
                        actions=[
                            ClipAction(
                                "Copy provided filename",
                                str(abbreviations_path),
                            )
                        ],
                    )
                )

                return

            # do fuzzy search on both the abbreviations and their description
            matched = process.extract(query_str, abbr_latest_d_bi.keys(), limit=10)
            for m in [elem[0] for elem in matched]:
                if m in abbr_latest_d.keys():
                    query.add(get_abbr_as_item((m, abbr_latest_d[m])))
                else:
                    query.add(get_abbr_as_item((abbr_latest_d_bi[m], m)))

        except Exception:  # user to report error
            if dev_mode:  # let exceptions fly!
                print(traceback.format_exc())
                raise

            query.add(
                v0.Item(
                    id=md_name,
                    icon=[icon_path],
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        ClipAction(
                            f"Copy error - report it to {md_url[8:]}",
                            f"{traceback.format_exc()}",
                        )
                    ],
                ),
            )
