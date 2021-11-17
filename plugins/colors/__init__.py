"""Visualise color codes."""

# TODO name autocomplete
# TODO on color selection show
#   RGB
#   YCMK
#   HSL
#   Similar colors

import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np

import colour
from colour import Color
from fuzzywuzzy import process
import albert as v0

__title__ = "Color Codes visualisation"
__version__ = "0.4.0"
__triggers__ = "col "
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/colors"
)

icon_path = str(Path(__file__).parent / "colors")

cache_path = Path(v0.cacheLocation()) / "colors"
config_path = Path(v0.configLocation()) / "colors"
data_path = Path(v0.dataLocation()) / "colors"
dev_mode = True

color_names = colour.COLOR_NAME_TO_RGB.keys()
h_values = [Color(c).get_hex() for c in color_names]
color_names_and_hex = list(color_names) + h_values
h_to_color_name = {h: c for h, c in zip(h_values, color_names)}


# plugin main functions -----------------------------------------------------------------------


def initialize():
    """Called when the extension is loaded (ticked in the settings) - blocking."""

    # create plugin locations
    for p in (cache_path, config_path, data_path):
        p.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


def handleQuery(query) -> list:
    """Hook that is called by albert with *every new keypress*."""  # noqa
    results = []

    if query.isTriggered:
        try:
            query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            query_str = query.string.strip()

            if not query_str:
                results.append(
                    v0.Item(
                        id=__title__,
                        icon=icon_path,
                        text="Give me color name, rgb triad or hex value",
                        subtext="supports fuzzy-search...",
                    )
                )
                return results

            # see if the name matches a color exactly
            color = get_as_color(query_str)
            if color:
                results.append(get_as_item(color))
                return results

            # no exact match
            matched = process.extract(query_str, list(color_names_and_hex), limit=10)
            for m in [elem[0] for elem in matched]:
                results.append(get_as_item(Color(m)))

        except Exception:  # user to report error
            if dev_mode:  # let exceptions fly!
                print(traceback.format_exc())
                raise

            results.insert(
                0,
                v0.Item(
                    id=__title__,
                    icon=icon_path,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        v0.ClipAction(
                            f"Copy error - report it to {__homepage__[8:]}",
                            f"{traceback.format_exc()}",
                        )
                    ],
                ),
            )

    return results


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
    thumbnail_size = (5, 5)
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
        name = f"| {h_to_color_name[hl]}"
    else:
        name = ""

    actions = [
        v0.ClipAction("Copy Hex (Long)", hl),
        v0.ClipAction("Copy RGB", f"{rgb}"),
        v0.ClipAction("Copy RGB [0, 1]", f"{color.get_rgb()}"),
    ]

    h = color.get_hex()
    if h != hl:
        actions.insert(0, v0.ClipAction("Copy Hex (Short)", h))

    return v0.Item(
        id=__title__,
        icon=img_path,
        text=f'<p style="color:{hl}";>{hl}{name}</p>',
        subtext=f"{rgb}",
        completion=" ".join([__triggers__, h]),
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


def setup(query):
    """Setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []
    return results
