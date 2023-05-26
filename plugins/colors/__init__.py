"""Visualise color codes."""

# TODO on color selection show
#   RGB
#   YCMK
#   HSL
#   Similar colors

import traceback
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np

import colour
from colour import Color
from fuzzywuzzy import process
import albert as v0

md_name = "Color codes visualisation"
md_description = "Color codes visualisation"
md_iid = "0.5"
md_version = "0.5"
md_maintainers = "Nikos Koukis"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/colors"

icon_path = str(Path(__file__).parent / "colors")

cache_path = Path(v0.cacheLocation()) / "colors"
config_path = Path(v0.configLocation()) / "colors"
data_path = Path(v0.dataLocation()) / "colors"
dev_mode = True

color_names = colour.COLOR_NAME_TO_RGB.keys()
h_values = [Color(c).get_hex() for c in color_names]
color_names_and_hex = list(color_names) + h_values
h_to_color_name = {h: c for h, c in zip(h_values, color_names)}


# supplementary functions ---------------------------------------------------------------------
def get_color_thumbnail(color: Color) -> Path:
    """
    Retrieve the thumbnail of the given color. The output name will be the corresponding hex
    strings. If the corresponding file does not exist, it will create it.
    """

    fname = data_path / (str(color.get_hex_l()[1:]) + ".png")
    if fname.exists():
        if fname.is_file():
            return fname
        else:
            raise FileNotFoundError(f"Thumbnail file exists but it's not a file -> {fname}")

    # file not there - cache it
    thumbnail_size = (50, 50)
    rgb_triad = np.array([c * 255 for c in color.get_rgb()], dtype=np.uint8)
    mat = np.zeros((*thumbnail_size, 3), dtype=np.uint8) + rgb_triad

    plt.imsave(fname, mat)
    return fname


def get_as_item(color):
    """Return an item - ready to be appended to the items list and be rendered by Albert."""
    img_path = str(get_color_thumbnail(color))

    rgb = [int(i * 255) for i in color.get_rgb()]
    hl = color.get_hex_l()
    if hl in h_to_color_name:
        name = f" | {h_to_color_name[hl]}"
    else:
        name = ""

    actions = [
        ClipAction("Copy Hex (Long)", hl),
        ClipAction("Copy RGB", f"{rgb}"),
        ClipAction("Copy RGB [0, 1]", f"{color.get_rgb()}"),
    ]

    h = color.get_hex()
    if h != hl:
        actions.insert(0, ClipAction("Copy Hex (Short)", h))

    return v0.Item(
        id=f"{md_name}_{hl}",
        icon=[img_path],
        text=f"{hl}{name}",
        subtext=f"{rgb}",
        actions=actions,
    )


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


def save_data(data: str, data_name: str):
    """Save a piece of data in the configuration directory."""
    with open(config_path / data_name, "w") as f:
        f.write(data)


def load_data(data_name) -> str:
    """Load a piece of data from the configuration directory."""
    with open(config_path / data_name, "r") as f:
        data = f.readline().strip().split()[0]

    return data


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
        return "col "

    def synopsis(self):
        return "some color description ..."

    def initialize(self):
        """Called when the extension is loaded (ticked in the settings) - blocking."""

        # create plugin locations
        for p in (cache_path, config_path, data_path):
            p.mkdir(parents=False, exist_ok=True)

    def finalize(self):
        pass

    def handleQuery(self, query) -> None:
        """Hook that is called by albert with *every new keypress*."""  # noqa
        try:
            query_str = query.string.strip()

            if not query_str:
                query.add(
                    v0.Item(
                        id=md_name,
                        icon=[icon_path],
                        text="Give me color name, rgb triad or hex value",
                        subtext="supports fuzzy-search...",
                    )
                )
                return

            # see if the name matches a color exactly
            color = get_as_color(query_str)
            if color:
                query.add(get_as_item(color))
                return

            # no exact match
            matched = process.extract(query_str, list(color_names_and_hex), limit=10)
            query.add([get_as_item(Color(elem[0])) for elem in matched])

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
