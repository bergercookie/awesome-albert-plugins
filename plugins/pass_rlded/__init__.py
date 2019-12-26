"""Access UNIX Password Manager Items using fuzzy search."""

from pathlib import Path
import os
import subprocess
import sys
from typing import Iterable

from fuzzywuzzy import process
import albertv0 as v0
import shutil

__iid__ = "PythonInterface/v0.2"
__prettyname__ = "Pass - UNIX Password Manager - fuzzy search"
__version__ = "0.1.0"
__trigger__ = "pass2 "
__author__ = "Nikos Koukis"
__dependencies__ = []
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/pass_rlded"
)

icon_path = os.path.join(os.path.dirname(__file__), "pass_rlded")

cache_path = Path(v0.cacheLocation()) / "pass_rlded"
config_path = Path(v0.configLocation()) / "pass_rlded"
data_path = Path(v0.dataLocation()) / "pass_rlded"


pass_dir = Path(
    os.environ.get(
        "PASSWORD_STORE_DIR", os.path.join(os.path.expanduser("~/.password-store/"))
    )
)


# passwords cache -----------------------------------------------------------------------------
class PasswordsCacheManager:
    def __init__(self):
        self.refresh = True

    def get_all_gpg_files(self, root: Path) -> Iterable[Path]:
        """Get a list of all the ggp-encrypted files under the given dir."""
        self.refresh = False
        return root.rglob("**/*.gpg")

    def signal_refresh(self):
        self.refresh = True


passwords_cache = PasswordsCacheManager()

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

            query_str = query.string.strip()
            if len(query_str) == 0:
                # refresh the passwords cache
                passwords_cache.signal_refresh()

            # build a list of all the paths under pass_dir
            gpg_files = passwords_cache.get_all_gpg_files(pass_dir)

            # fuzzy search on the paths list
            matched = process.extract(query_str, gpg_files, limit=10)
            for m in [elem[0] for elem in matched]:
                results.append(get_as_item(m))

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


def get_as_item(password_path: Path):
    full_path_no_suffix = Path(f"{password_path.parent}/{password_path.stem}")
    full_path_rel_root = full_path_no_suffix.relative_to(pass_dir)

    full_path_no_suffix_str = str(full_path_no_suffix)
    full_path_rel_root_str = str(full_path_rel_root)

    return v0.Item(
        id=__prettyname__,
        icon=icon_path,
        text=f"{password_path.stem}",
        subtext=full_path_no_suffix_str,
        completion=f"{__trigger__} {full_path_no_suffix_str}",
        actions=[
            v0.ProcAction("Copy", ["pass", "--clip", full_path_rel_root_str]),
            v0.ProcAction("Edit", ["pass", "edit", full_path_rel_root_str]),
            v0.ProcAction("Remove", ["pass", "rm", "--force", full_path_rel_root_str]),
            # v0.ProcAction("Decrypt and open document", )
            v0.ClipAction("Copy Full Path", str(password_path)),
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
