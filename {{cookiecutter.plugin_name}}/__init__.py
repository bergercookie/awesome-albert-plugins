""" {{ cookiecutter.plugin_short_description }} """

from pathlib import Path
import sys
import os

import albertv0 as v0

__iid__ = "PythonInterface/{{ cookiecutter.albert_plugin_interface }}"
__prettyname__ = "{{ cookiecutter.plugin_short_description }}"
__version__ = "{{ cookiecutter.version }}"
__trigger__ = "{{ cookiecutter.plugin_name }} "
__author__ = "{{ cookiecutter.author }}"
__dependencies__ = []
__homepage__ = "{{ cookiecutter.repo_base_url }}/{{ cookiecutter.repo_name }}"

icon_path = v0.iconLookup("{{ cookiecutter.plugin_name }}")
if not icon_path:
    icon_path = os.path.join(os.path.dirname(__file__), "{{ cookiecutter.plugin_name }}")
settings_path = Path(v0.cacheLocation()) / " {{ cookiecutter.plugin_name }}"


def initialize():
    # Called when the extension is loaded (ticked in the settings) - blocking

    # create cache location
    settings_path.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


def handleQuery(query):
    results = []

    if query.isTriggered:
        try:
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
