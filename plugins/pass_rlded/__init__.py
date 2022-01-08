"""Access UNIX Password Manager Items using fuzzy search."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import albert as v0
from fuzzywuzzy import process

__title__ = "Pass - UNIX Password Manager - fuzzy search"
__version__ = "0.4.0"
__triggers__ = "pass "
__authors__ = "Nikos Koukis"
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

# https://gist.github.com/bergercookie/d808bade22e62afbb2abe64fb1d20688
# For an updated version feel free to contact me.
pass_open_doc = shutil.which("pass_open_doc")
pass_open_doc_exts = [
    ".jpg",
    ".jpeg",
    ".pdf",
    ".png",
]

dev_mode = True


def pass_open_doc_compatible(path: Path) -> bool:
    """Determine if the given path can be opened via pass_open_doc."""
    if not shutil.which("pass-open-doc"):
        return False

    return len(path.suffixes) >= 2 and path.suffixes[-2] in pass_open_doc_exts


# passwords cache -----------------------------------------------------------------------------
class PasswordsCacheManager:
    def __init__(self, pass_dir: Path):
        self.refresh = True
        self._pass_dir = pass_dir

    def _refresh_passwords(self) -> Sequence[Path]:
        passwords = tuple(self._pass_dir.rglob("**/*.gpg"))
        save_data("\n".join((str(p) for p in passwords)), "password_paths")

        return passwords

    def get_all_gpg_files(self) -> Sequence[Path]:
        """Get a list of all the ggp-encrypted files under the given dir."""
        passwords: Sequence[Path]
        if self.refresh == True or not data_exists("password_paths"):
            passwords = self._refresh_passwords()
            self.refresh = False
        else:
            passwords = tuple(Path(p) for p in load_data("password_paths"))

        return passwords


passwords_cache = PasswordsCacheManager(pass_dir=pass_dir)

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
            query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            query_str = query.string.strip()
            if len(query_str) == 0:
                passwords_cache.refresh = True

            # get a list of all the paths under pass_dir
            gpg_files = passwords_cache.get_all_gpg_files()

            # fuzzy search on the paths list
            matched = process.extract(query_str, gpg_files, limit=10)
            for m in [elem[0] for elem in matched]:
                results.append(get_as_item(m))

        except Exception:  # user to report error
            if dev_mode:
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

    actions = [
        v0.ProcAction("Remove", ["pass", "rm", "--force", full_path_rel_root_str]),
        v0.ClipAction("Copy Full Path", str(password_path)),
        v0.ClipAction(
            "Copy pass-compatible path",
            str(password_path.relative_to(pass_dir).parent / password_path.stem),
        ),
    ]

    if pass_open_doc_compatible(password_path):
        actions.insert(
            0,
            v0.FuncAction(
                "Open document with pass-open-doc",
                lambda p=str(password_path): subprocess.run(["pass-open-doc", p], check=True),
            ),
        )
    else:
        actions.insert(0, v0.ProcAction("Edit", ["pass", "edit", full_path_rel_root_str]))
        actions.insert(
            0,
            v0.ProcAction("Copy", ["pass", "--clip", full_path_rel_root_str]),
        )

    return v0.Item(
        id=__title__,
        icon=icon_path,
        text=f"{password_path.stem}",
        subtext=full_path_no_suffix_str,
        completion=f"{__triggers__} {full_path_no_suffix_str}",
        actions=actions,
    )


def get_as_subtext_field(field, field_title=None) -> str:
    """Get a certain variable as part of the subtext, along with a title for that variable."""
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


def load_data(data_name: str) -> Sequence[str]:
    """Load a piece of data from the configuration directory."""
    with open(config_path / data_name, "r") as f:
        return [s.strip() for s in f.readlines()]


def data_exists(data_name: str) -> bool:
    return (config_path / data_name).is_file()


def setup(query):
    """setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []
    return results
