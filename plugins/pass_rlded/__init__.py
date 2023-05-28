"""Access UNIX Password Manager Items using fuzzy search."""

import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Sequence

import albert as v0
import gi
from fuzzywuzzy import process

gi.require_version("Notify", "0.7")  # isort:skip
gi.require_version("GdkPixbuf", "2.0")  # isort:skip
from gi.repository import GdkPixbuf, Notify  # isort:skip  # type: ignore

md_name = "Pass"
md_description = "Pass - UNIX Password Manager - fuzzy search"
md_iid = "0.5"
md_version = "0.2"
md_maintainers = "Nikos Koukis"
md_url = (
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
        if self.refresh is True or not data_exists("password_paths"):
            passwords = self._refresh_passwords()
            self.refresh = False
        else:
            passwords = tuple(Path(p) for p in load_data("password_paths"))

        return passwords


passwords_cache = PasswordsCacheManager(pass_dir=pass_dir)


# plugin main functions -----------------------------------------------------------------------
def do_notify(msg: str, image=None):
    app_name = "pass_rlded"
    Notify.init(app_name)
    image = image
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def generate_passwd_cmd(passwd_name: str) -> str:
    return f"pass generate -c -f {passwd_name}"


def generate_passwd_cmd_li(passwd_name: str) -> Sequence[str]:
    return f"pass generate -c -f {passwd_name}".split()


# supplementary functions ---------------------------------------------------------------------


def get_as_item(query, password_path: Path):
    full_path_no_suffix = Path(f"{password_path.parent}/{password_path.stem}")
    full_path_rel_root = full_path_no_suffix.relative_to(pass_dir)

    full_path_rel_root_str = str(full_path_rel_root)

    actions = [
        ProcAction("Remove", ["pass", "rm", "--force", full_path_rel_root_str]),
        ClipAction("Copy Full Path", str(password_path)),
        ClipAction("Copy Password name", password_path.name),
        ClipAction("Copy pass-compatible path", full_path_rel_root_str),
    ]

    actions.insert(0, ProcAction("Edit", ["pass", "edit", full_path_rel_root_str]))
    actions.insert(
        0,
        ProcAction("Copy", ["pass", "--clip", full_path_rel_root_str]),
    )

    if pass_open_doc_compatible(password_path):
        actions.insert(
            0,
            FuncAction(
                "Open document with pass-open-doc",
                lambda p=str(password_path): subprocess.run(["pass-open-doc", p], check=True),
            ),
        )

    return v0.Item(
        id=md_name,
        icon=[icon_path],
        text=f"{password_path.stem}",
        subtext=full_path_rel_root_str,
        completion=f"{query.trigger}{full_path_rel_root_str}",
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

class ProcAction(v0.Action):
    def __init__(self, name, args):
        super().__init__(name, name, lambda: v0.runDetachedProcess(args))


# main plugin class ------------------------------------------------------------
class Plugin(v0.QueryHandler):
    def id(self) -> str:
        return __name__

    def name(self) -> str:
        return md_name

    def description(self):
        return md_description

    def defaultTrigger(self):
        return "pass "

    def synopsis(self):
        return "pass name"

    def initialize(self):
        # Called when the extension is loaded (ticked in the settings) - blocking

        # create plugin locations
        for p in (cache_path, config_path, data_path):
            p.mkdir(parents=False, exist_ok=True)

    def finalize(self):
        pass

    def handleQuery(self, query) -> None:
        results = []

        try:
            query_str = query.string.strip()
            if len(query_str) == 0:
                passwords_cache.refresh = True
                results.append(
                    v0.Item(
                        id=md_name,
                        icon=[icon_path],
                        text="Continue typing to fuzzy-search on passwords...",
                        actions=[],
                    )
                )
                results.append(
                    v0.Item(
                        id=md_name,
                        icon=[icon_path],
                        text="Generate a new password...",
                        completion=f"{query.trigger}generate",
                        actions=[],
                    )
                )

            if query_str.startswith("generate"):
                if len(query_str) > 1:
                    passwd_name = " ".join(query_str.split()[1:])
                    results.insert(
                        0,
                        v0.Item(
                            id=md_name,
                            icon=[icon_path],
                            text="Generate new password",
                            subtext=generate_passwd_cmd(passwd_name),
                            completion=f"{query.trigger}{query_str}",
                            actions=[
                                ProcAction(
                                    "Generate new password",
                                    generate_passwd_cmd_li(passwd_name=passwd_name),
                                )
                            ],
                        ),
                    )
                else:
                    results.append(
                        v0.Item(
                            id=md_name,
                            icon=[icon_path],
                            text="What's the path of this new password?",
                            subtext="e.g., awesome-e-shop/johndoe@mail.com",
                            completion=f"{query.trigger} generate",
                            actions=[],
                        )
                    )

            # get a list of all the paths under pass_dir
            gpg_files = passwords_cache.get_all_gpg_files()

            # fuzzy search on the paths list
            matched = process.extract(query_str, gpg_files, limit=10)
            for m in [elem[0] for elem in matched]:
                results.append(get_as_item(query, m))

        except Exception:  # user to report error
            print(traceback.format_exc())

            results.insert(
                0,
                v0.Item(
                    id=md_name,
                    icon=[icon_path],
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        ClipAction(
                            f"Copy error - report it to {md_url[8:]}",
                            f"{sys.exc_info()}",
                        )
                    ],
                ),
            )

        query.add(results)

