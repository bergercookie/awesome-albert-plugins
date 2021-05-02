"""Meme Generator - Generate memes with custom quotes - ready to be copied / uploaded / shared at an instant."""

from pathlib import Path
from typing import List, Dict
import os
import shutil
import subprocess
import sys
import time
import traceback

from fuzzywuzzy import process
from gi.repository import GdkPixbuf, Notify

import albert as v0

__title__ = "Meme Generator - Generate memes with custom quotes - ready to be copied / uploaded / shared at an instant"
__version__ = "0.4.0"
__triggers__ = "meme "
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/meme-generator"
)
__exec_deps__ = ["meme", "xclip"]
__py_deps__ = ["shutil", "fuzzywuzzy"]

icon_path = str(Path(__file__).parent / "meme-generator")

cache_path = Path(v0.cacheLocation()) / "meme-generator"
config_path = Path(v0.configLocation()) / "meme-generator"
data_path = Path(v0.dataLocation()) / "meme-generator"
dev_mode = True

# plugin main functions -----------------------------------------------------------------------


def initialize():
    """Called when the extension is loaded (ticked in the settings) - blocking."""

    # create plugin locations
    for p in (cache_path, config_path, data_path):
        p.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


def import_template_ids() -> List[str]:
    """Return a list of all the supported template IDs."""
    return subprocess.check_output(["meme", "-list-templates"]).decode("utf-8").splitlines()


def get_template_img(meme_id: str) -> Path:
    """Get the path to the template image, given the template meme ID."""
    # may be a bit fragile - TODO Find a better way to do it.
    bin_path = Path(shutil.which("meme")).parent  # type: ignore
    meme_reg_path = bin_path.parent / "pkg" / "mod" / "github.com" / "nomad-software"
    meme_reg_versions = list(meme_reg_path.glob("meme@*"))

    if not meme_reg_versions:
        raise RuntimeError(f'Can\'t find any Go "meme" packages under {meme_reg_path}')

    # use the most recent versions
    return meme_reg_versions[0] / "data" / "images" / f"{meme_id}.jpg"


class Template:
    def __init__(self, id: str):
        self.id = id
        self.img = get_template_img(id)

    def title(self) -> str:
        return self.id.replace("-", " ").capitalize()

    def get_as_item(self):
        """Return it as item - ready to be appended to the items list and be rendered by
        Albert.
        """
        return v0.Item(
            id=__title__,
            icon=str(self.img),
            text=self.title(),
            subtext="",
            completion=f"{__triggers__} {self.id} ",
            actions=[
                v0.FuncAction("Copy vanilla image", lambda: self.copy_vanilla_img()),
                v0.ClipAction("Copy vanilla image path", str(self.img)),
            ],
        )

    def _create_custom_meme(self, caption1: str, caption2: str) -> Path:
        output = "/tmp/albert-meme.png"
        subprocess.check_call(
            ["meme", "-i", self.id, "-o", output, "-t", f"{caption1}|{caption2}"]
        )

        return Path(output)

    def _create_n_copy_to_clipboard(self, caption1: str, caption2: str):
        p = self._create_custom_meme(caption1=caption1, caption2=caption2)
        subprocess.check_call(["xclip", "-selection", "clipboard", "-t", "image/png", str(p)])

    def _create_n_copy_path_to_clipboard(self, caption1: str, caption2: str):
        p = self._create_custom_meme(caption1=caption1, caption2=caption2)
        subprocess.Popen(f"echo {p}| xclip -selection clipboard", shell=True)

    def get_as_item_custom(self, caption1=None, caption2=None):
        if caption1 or caption2:
            subtext = f"UP: {caption1} | DOWN: {caption2}"
        else:
            subtext = "USAGE: {self.id} [upper-text] | [lower-text]"
        return v0.Item(
            id=__title__,
            icon=str(self.img),
            text=self.title(),
            subtext=subtext,
            completion=f"{__triggers__} {self.id} ",
            actions=[
                v0.FuncAction(
                    "Copy generated custom meme to clipboard",
                    lambda caption1=caption1, caption2=caption2: self._create_n_copy_to_clipboard(
                        caption1=caption1, caption2=caption2
                    ),
                ),
                v0.FuncAction(
                    "Copy generated custom meme path",
                    lambda caption1=caption1, caption2=caption2: str(
                        self._create_n_copy_path_to_clipboard(
                            caption1=caption1, caption2=caption2
                        )
                    ),
                ),
            ],
        )

    def copy_vanilla_img(self):
        fname_out = "/tmp/meme.png"
        subprocess.check_call(["convert", "-format", "png", str(self.img), fname_out])
        subprocess.check_call(
            ["xclip", "-selection", "clipboard", "-t", "image/png", fname_out]
        )


all_templates = [Template(id=id) for id in import_template_ids()]
id_to_template = {template.id: template for template in all_templates}


def handleQuery(query) -> list:
    """Hook that is called by albert with *every new keypress*."""  # noqa
    results = []

    if query.isTriggered:
        try:
            query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            query_str = query.string
            query_parts = query_str.split()

            if not query_parts:
                for template in all_templates:
                    results.append(template.get_as_item())

                return results

            meme_id = query_parts[0]
            if meme_id in id_to_template:
                captions = [c.strip() for c in " ".join(query_parts[1:]).split("|")]
                c1 = captions[0]
                c2 = captions[1] if len(captions) > 1 else ""
                results.insert(
                    0,
                    id_to_template[meme_id].get_as_item_custom(caption1=c1, caption2=c2),
                )
            else:
                title_to_templ = {template.title(): template for template in all_templates}
                # do fuzzy search - show relevant issues
                matched = process.extract(
                    query.string.strip(), list(title_to_templ.keys()), limit=5
                )
                for m in [elem[0] for elem in matched]:
                    results.append(title_to_templ[m].get_as_item())

        except Exception:  # user to report error
            if dev_mode:  # let exceptions fly!
                v0.critical(traceback.format_exc())
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
def notify(
    msg: str,
    app_name: str = __title__,
    image=str(icon_path),
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
