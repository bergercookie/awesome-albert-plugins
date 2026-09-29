"""Scratchpad - Dump all your thoughts into a single textfile."""

import textwrap
import traceback
from pathlib import Path
from typing import Iterator, List

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
md_name = "Scratchpad"
md_description = "Scratchpad - Dump all your thoughts into a single textfile"
md_url = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/scratchpad"
)
md_maintainers = ["Nikos Koukis"]

ICON_PATH = Path(__file__).parent / "scratchpad.svg"

# break long lines at the specified width
split_at_textwidth = 80


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

        self.s_store_fname = self.config_path / "fname"
        self.s_path = Path()

        self.load_settings()

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "s "

    def synopsis(self, query):
        return "add text to scratchpad"

    def load_settings(self) -> None:
        """Read back the scratchpad file given in a previous run."""
        if self.s_store_fname.is_file():
            with open(self.s_store_fname, "r") as f:
                p = Path(f.readline().strip()).expanduser()
                self.s_path = p if p.is_file() else Path()

    def save_to_scratchpad(self, line: str, sep=False):
        with open(self.s_path, "a+") as f:
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

    def get_as_item(self, ctx) -> StandardItem:
        """Return an item - ready to be appended to the items list and be rendered by Albert."""
        query_str = ctx.query.strip()
        return StandardItem(
            id=f"scratchpad-save-{query_str}",
            icon_factory=self.makeIcon,
            text="Save to scratchpad",
            subtext=query_str,
            input_action_text=f"{ctx.trigger}{query_str}",
            actions=[
                Action(
                    "save",
                    f"Save to scratchpad ➡️ {self.s_path}",
                    lambda line=query_str: self.save_to_scratchpad(line),
                ),
                Action(
                    "save-section",
                    f"Save to scratchpad - New Section ➡️ {self.s_path}",
                    lambda line=query_str: self.save_to_scratchpad(line, sep=True),
                ),
            ],
        )

    def submit_fname(self, p: Path):
        p = p.expanduser().resolve()
        with open(self.s_store_fname, "w") as f:
            f.write(str(p))

        self.s_path = p

        # also create it
        self.s_path.touch()

    def setup(self, ctx) -> List[StandardItem]:
        """Setup is successful if an empty list is returned."""

        query_str = ctx.query

        # abbreviations file
        if not self.s_path.is_file():
            return [
                StandardItem(
                    id="scratchpad-setup-fname",
                    icon_factory=self.makeIcon,
                    text="Specify the location of the scratchpad file",
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

        return []

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        results = []

        # trigger if the user has either explicitly called the plugin or when we have detected
        # many words in the query. The latter is just a heuristic; I haven't decided whether
        # it's worth keeping
        if len(ctx.query.split()) < 4:
            return

        try:
            results_setup = self.setup(ctx)
            if results_setup:
                yield results_setup
                return

            results.append(self.get_as_item(ctx))

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)

            results.insert(
                0,
                StandardItem(
                    id="scratchpad-error",
                    icon_factory=self.makeIcon,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        Action(
                            "copy",
                            f"Copy error - report it to {md_url[8:]}",
                            lambda t=trace: setClipboardText(t),
                        )
                    ],
                ),
            )

        yield results
