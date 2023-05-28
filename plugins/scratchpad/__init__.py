"""Scratchpad - Dump all your thoughts into a single textfile."""

import textwrap
import traceback
from pathlib import Path

import albert as v0

md_name = "Scratchpad"
md_description = "Scratchpad - Dump all your thoughts into a single textfile"
md_iid = "0.5"
md_version = "0.2"
md_maintainers = "Nikos Koukis"
md_url = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/scratchpad"
)
md_bin_dependencies = []
md_lib_dependencies = ["textwrap"]

icon_path = str(Path(__file__).parent / "scratchpad")

cache_path = Path(v0.cacheLocation()) / "scratchpad"
config_path = Path(v0.configLocation()) / "scratchpad"
data_path = Path(v0.dataLocation()) / "scratchpad"

s_store_fname = config_path / "fname"

# break long lines at the specified width
split_at_textwidth = 80

# plugin main functions -----------------------------------------------------------------------
if s_store_fname.is_file():
    with open(s_store_fname, "r") as f:
        p = Path(f.readline().strip()).expanduser()
        s_path = p if p.is_file() else Path()


def save_to_scratchpad(line: str, sep=False):
    with open(s_path, "a+") as f:
        if split_at_textwidth is not None:
            towrite = textwrap.fill(line, split_at_textwidth)
        else:
            towrite = line

        towrite = f"\n{towrite}"

        s = ""
        if sep:
            s = "\n\n" + "-" * 10 + "\n"
            towrite = f"{s}{towrite}\n"

        towrite = f"{towrite}\n"
        f.write(towrite)


# supplementary functions ---------------------------------------------------------------------
def notify(
    msg: str,
    app_name: str = md_name,
    image=str(icon_path),
):
    Notify.init(app_name)
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def get_as_item(query):
    """Return an item - ready to be appended to the items list and be rendered by Albert."""
    query_str = query.string.strip()
    return v0.Item(
        id=md_name,
        icon=[icon_path],
        text="Save to scratchpad",
        subtext=query_str,
        completion=f"{query.trigger}{query_str}",
        actions=[
            FuncAction(
                f"Save to scratchpad ➡️ {s_path}",
                lambda line=query_str: save_to_scratchpad(line),
            ),
            FuncAction(
                f"Save to scratchpad - New Section ➡️ {s_path}",
                lambda line=query_str: save_to_scratchpad(line, sep=True),
            ),
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
    with open(s_store_fname, "w") as f:
        f.write(str(p))

    global s_path
    s_path = p

    # also create it
    s_path.touch()


def setup(query):
    """Setup is successful if an empty list is returned."""

    query_str = query.string

    # abbreviations file
    if not s_path.is_file():
        query.add(
            v0.Item(
                id=md_name,
                icon=[icon_path],
                text="Specify the location of the scratchpad file",
                subtext="Paste the path to the file, then press ENTER",
                actions=[
                    FuncAction("Submit path", lambda p=query_str: submit_fname(Path(p))),
                ],
            )
        )
        return True

    return False


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
        return "s "

    def synopsis(self):
        return "add text to scratchpad"

    def initialize(self):
        """Called when the extension is loaded (ticked in the settings) - blocking."""

        # create plugin locations
        for p in (cache_path, config_path, data_path):
            p.mkdir(parents=False, exist_ok=True)

    def finalize(self):
        pass

    def handleQuery(self, query) -> None:
        """Hook that is called by albert with *every new keypress*."""  # noqa
        results = []

        # trigger if the user has either explicitly called the plugin or when we have detected
        # many words in the query. The latter is just a heuristic; I haven't decided whether
        # it's worth keeping
        if len(query.string.split()) < 4:
            return

        try:
            results_setup = setup(query)
            if results_setup:
                return

            results.append(get_as_item(query))

        except Exception:  # user to report error
            v0.critical(traceback.format_exc())

            results.insert(
                0,
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

        query.add(results)
