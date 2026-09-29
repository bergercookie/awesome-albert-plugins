"""Visualise color codes."""

# TODO on color selection show
#   RGB
#   YCMK
#   HSL
#   Similar colors

import traceback
from pathlib import Path
from typing import Iterator, List, Optional

import colour
import matplotlib.pyplot as plt
import numpy as np
from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    PluginInstance,
    StandardItem,
    setClipboardText,
)
from colour import Color
from fuzzywuzzy import process

md_iid = "5.0"
md_version = "0.3"
md_name = "Color codes visualisation"
md_description = "Color codes visualisation"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/colors"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["colour", "fuzzywuzzy", "matplotlib", "numpy"]

ICON_PATH = Path(__file__).parent / "colors.png"

color_names = colour.COLOR_NAME_TO_RGB.keys()
h_values = [Color(c).get_hex() for c in color_names]
color_names_and_hex = list(color_names) + h_values
h_to_color_name = {h: c for h, c in zip(h_values, color_names)}


# supplementary functions ---------------------------------------------------------------------
def get_as_color(s: str) -> Optional[Color]:
    try:
        c = Color(s)
        return c
    except:
        return None


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

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "col "

    def synopsis(self, query):
        return "some color description ..."

    def get_color_thumbnail(self, color: Color) -> Path:
        """
        Retrieve the thumbnail of the given color. The output name will be the corresponding hex
        strings. If the corresponding file does not exist, it will create it.
        """

        fname = self.data_path / (str(color.get_hex_l()[1:]) + ".png")
        if fname.exists():
            if fname.is_file():
                return fname
            else:
                raise FileNotFoundError(
                    f"Thumbnail file exists but it's not a file -> {fname}"
                )

        # file not there - cache it
        thumbnail_size = (50, 50)
        rgb_triad = np.array([c * 255 for c in color.get_rgb()], dtype=np.uint8)
        mat = np.zeros((*thumbnail_size, 3), dtype=np.uint8) + rgb_triad

        plt.imsave(fname, mat)
        return fname

    def get_as_item(self, color, key: str = "") -> StandardItem:
        """Return an item - ready to be appended to the items list and be rendered by Albert.

        `key` is the string this item was matched on - it keeps the id unique for the fuzzy
        matches, since several color names may denote the very same color (e.g. gray/grey)
        """
        img_path = str(self.get_color_thumbnail(color))

        rgb = [int(i * 255) for i in color.get_rgb()]
        hl = color.get_hex_l()
        if hl in h_to_color_name:
            name = f" | {h_to_color_name[hl]}"
        else:
            name = ""

        actions = [
            Action("copy", "Copy Hex (Long)", lambda t=hl: setClipboardText(t)),
            Action("copy", "Copy RGB", lambda t=f"{rgb}": setClipboardText(t)),
            Action(
                "copy", "Copy RGB [0, 1]", lambda t=f"{color.get_rgb()}": setClipboardText(t)
            ),
        ]

        h = color.get_hex()
        if h != hl:
            actions.insert(
                0, Action("copy", "Copy Hex (Short)", lambda t=h: setClipboardText(t))
            )

        return StandardItem(
            id=f"colors-{hl[1:]}-{key}" if key else f"colors-{hl[1:]}",
            icon_factory=lambda p=img_path: Icon.image(p),
            text=f"{hl}{name}",
            subtext=f"{rgb}",
            actions=actions,
        )

    def save_data(self, data: str, data_name: str):
        """Save a piece of data in the configuration directory."""
        with open(self.config_path / data_name, "w") as f:
            f.write(data)

    def load_data(self, data_name) -> str:
        """Load a piece of data from the configuration directory."""
        with open(self.config_path / data_name, "r") as f:
            data = f.readline().strip().split()[0]

        return data

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        """Called by albert with *every new keypress*."""
        try:
            query_str = ctx.query.strip()

            if not query_str:
                yield [
                    StandardItem(
                        id="colors-hint",
                        icon_factory=self.makeIcon,
                        text="Give me color name, rgb triad or hex value",
                        subtext="supports fuzzy-search...",
                    )
                ]
                return

            # see if the name matches a color exactly
            color = get_as_color(query_str)
            if color:
                yield [self.get_as_item(color)]
                return

            # no exact match
            matched = process.extract(query_str, list(color_names_and_hex), limit=10)
            yield [self.get_as_item(Color(elem[0]), elem[0]) for elem in matched]

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)

            yield [
                StandardItem(
                    id="colors-error",
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
