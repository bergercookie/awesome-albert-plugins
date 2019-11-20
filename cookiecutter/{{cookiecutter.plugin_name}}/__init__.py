"""{{ cookiecutter.plugin_short_description }}."""

from pathlib import Path
import os
import subprocess
import sys

from fuzzywuzzy import process
import albertv0 as v0
import shutil

__iid__ = "PythonInterface/{{ cookiecutter.albert_plugin_interface }}"
__prettyname__ = "{{ cookiecutter.plugin_short_description }}"
__version__ = "{{ cookiecutter.version }}"
__trigger__ = "{{ cookiecutter.plugin_name }} "
__author__ = "{{ cookiecutter.author }}"
__dependencies__ = []
__homepage__ = "{{ cookiecutter.repo_base_url }}/{{ cookiecutter.plugin_name }}"

icon_path = v0.iconLookup("{{ cookiecutter.plugin_name }}")
if not icon_path:
    icon_path = os.path.join(os.path.dirname(__file__), "{{ cookiecutter.plugin_name }}")

cache_path = Path(v0.cacheLocation()) / "{{ cookiecutter.plugin_name }}"
config_path = Path(v0.configLocation()) / "{{ cookiecutter.plugin_name }}"
data_path = Path(v0.dataLocation()) / "{{ cookiecutter.plugin_name }}"

# plugin main functions -----------------------------------------------------------------------


def initialize():
    # Called when the extension is loaded (ticked in the settings) - blocking

    # create plugin locations
    for p in (cache_path, config_path, data_path):
        p.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


def handleQuery(query):
    results = []

    if query.isTriggered:
        try:
            # be backwards compatible with v0.2
            if "disableSort" in dir(query):
                query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            # modify this...
            results.append(get_as_item())

        except Exception:  # user to report error
            results.insert(
                0,
                v0.Item(
                    id=__prettyname__,
                    icon=icon_path,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        v0.ClipAction(
                            f"Copy error - report it to {__homepage__[8:]}",
                            f"{sys.exc_info()}",
                        )
                    ],
                ),
            )

    return results


# supplementary functions ---------------------------------------------------------------------


def get_as_item():
    return v0.Item(
        id=__prettyname__,
        icon=icon_path,
        text=f"{sys.version}",
        subtext="Python version",
        completion="",
        actions=[
            v0.UrlAction("Open in xkcd.com", "https://www.xkcd.com/"),
            v0.ClipAction("Copy URL", f"https://www.xkcd.com/"),
        ],
    )


def get_as_subtext_field(field, field_title=None) -> str:
    """Get a certain variable as part of the subtext, along with a title for that variable.

    """
    s = ""
    if field:
        s = f"{field} | "
    else:
        return ""

    if field_title:
        s = f"{field_title} :" + s

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
    """setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []
    return results
