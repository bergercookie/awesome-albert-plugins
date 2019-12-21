#!/usr/bin/env python3

"""
Create an albert python plugin for each one of the specified websites.
Uses the `googler` tool for the actual search.
"""

import os
import re
import secrets
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from subprocess import Popen
from typing import Optional

import requests

from cookiecutter.main import cookiecutter

# globals -------------------------------------------------------------------------------------

# Get all the websites that work with googler or manually specify websites to create a plugin
# for.
generate_plugins_only_for = [
    "alternativeto",
    "amazon",
    "askubuntu",
    "aur.archlinux",
    "bbc",
    "cnn",
    "cracked",
    "crunchbase",
    "distrowatch",
    "dpkg",
    "ebay",
    "facebook",
    "github",
    "gnu",
    "hackaday",
    "howstuffworks",
    "imdb",
    "kernel",
    "last",
    "linkedin",
    "linux",
    "opensubtitles",
    "python",
    "quora",
    "reddit",
    "rottentomatoes",
    "sourceforge",
    "stackoverflow",
    "ted",
    "wiki.archlinux",
    "wikipedia",
    "wikiquote",
    "yahoo",
    "youtube",
]

custom_plugins = {
    "search_amazon": {"trigger": "ama", "googler_at": "amazon.co.uk"},
    "search_google": {"trigger": "gg", "googler_at": ""},
    "search_cppreference": {"trigger": "cpp", "googler_at": "en.cppreference.com"},
}


# generate_plugins_only_for = []

# supplementary methods -----------------------------------------------------------------------


def get_plugin_name_wo_search(plugin_name):
    return plugin_name[len("search_") :]


def parse_googler_at_line(line: str):
    """Parse lines of this form:

        alias @zdnet='googler -w zdnet.com'\n
    """
    tokens = line.strip().split()
    googler_at = tokens[-1][:-1]  # ignore "'" in the end of line
    plugin_name = googler_at.split(".")[0]
    trigger = re.search("@(.*)=", line).groups()[0]

    return plugin_name, googler_at, trigger


def googler_plugins() -> dict:
    res = requests.get(
        "https://raw.githubusercontent.com/jarun/googler/master/auto-completion/googler_at/googler_at"
    )
    alias_lines = [
        l for l in res.text.splitlines() if "alias" in l and not l.lstrip().startswith("#")
    ]
    googler_plugins = {}

    for l in alias_lines:
        plugin_name, googler_at, trigger = parse_googler_at_line(l)
        plugin_name = "_".join(["search", plugin_name])

        googler_plugins[plugin_name] = {"googler_at": googler_at, "trigger": trigger}

    # user-specified filter
    if generate_plugins_only_for:
        googler_plugins = {
            g[0]: g[1]
            for g in googler_plugins.items()
            if get_plugin_name_wo_search(g[0]) in generate_plugins_only_for
        }

    return googler_plugins


def get_cookiecutter_directives(plugin_name, trigger, googler_at):
    github_user = "bergercookie"

    cookiecutter_directives = {
        "author": "Nikos Koukis",
        "plugin_name": plugin_name,
        "trigger": trigger,
        "googler_at": googler_at,
        "github_user": github_user,
        "repo_base_url": f"https://github.com/{github_user}/awesome-albert-plugins/blob/master/plugins/",
        "download_url_base": f"https://raw.githubusercontent.com/{github_user}/awesome-albert-plugins/master/plugins/{plugin_name}/",
        "plugin_short_description": f'{plugin_name.split("_")[1].capitalize()}: Search suggestions for {plugin_name.split("_")[1].capitalize()}',
        "albert_plugin_interface": "v0.2",
        "version": "0.1.0",
    }

    return cookiecutter_directives


# main ----------------------------------------------------------------------------------------


def main():
    # setup -----------------------------------------------------------------------------------
    cookiecutter_orig_path = Path(__file__).parent / "plugins" / "search_template"
    assert cookiecutter_orig_path.is_dir(), f"No such directory -> {cookiecutter_orig_path}"

    def get_logo(plugin_name) -> Optional[Path]:
        """Get the corresponding logo or None if the latter is not found."""
        p = (
            Path(__file__).parent
            / "googler_logos"
            / f"{get_plugin_name_wo_search(plugin_name)}.svg"
        )
        if not p.is_file():
            p = Path(__file__).parent / "googler_logos" / "default.svg"

        return p

    def get_output_dir(plugin_name) -> Path:
        """Get the output directory for the plugin at hand."""
        return Path(__file__).parent / "plugins" / plugin_name

    oldpwd = Path(".").absolute()
    os.chdir(Path(__file__).parent)

    # main functionality ----------------------------------------------------------------------
    plugins = googler_plugins()
    plugins.update(custom_plugins)
    for plugin in plugins.items():
        plugin_name = plugin[0]
        trigger = plugin[1]["trigger"]
        googler_at = plugin[1]["googler_at"]

        print()
        print("===============================================")
        print(f"Generating plugin -> {plugin_name}")
        print("===============================================")
        print()

        # create temporary template directory
        random_int = secrets.randbits(32)
        cookiecutter_tmp = PurePosixPath("/tmp") / f"albert-cookiecutter-{random_int}"
        shutil.copytree(cookiecutter_orig_path, cookiecutter_tmp)

        print(f"- Cookiecutter template directory -> {cookiecutter_tmp}")
        print(f"- Plugin output directory-> {get_output_dir(plugin_name)}")

        cookiecutter(
            template=str(cookiecutter_tmp),
            no_input=True,
            overwrite_if_exists=True,
            extra_context=get_cookiecutter_directives(
                plugin_name=plugin_name, trigger=trigger, googler_at=googler_at
            ),
            output_dir=get_output_dir(plugin_name).parent,
        )

        # copy logo if exists
        shutil.copy(get_logo(plugin_name), get_output_dir(plugin_name) / f"{plugin_name}.svg")

    # postprocessing --------------------------------------------------------------------------
    os.chdir(oldpwd)

    # TODO Remove temporary cookiecutter file and directories?


if __name__ == "__main__":
    main()
