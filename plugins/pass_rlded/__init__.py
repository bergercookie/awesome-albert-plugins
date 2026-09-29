"""Access UNIX Password Manager Items using fuzzy search."""

import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Iterator, List, Sequence

from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    Notification,
    PluginInstance,
    StandardItem,
    runDetachedProcess,
    setClipboardText,
)
from fuzzywuzzy import process

md_iid = "5.0"
md_version = "0.3"
md_name = "Pass"
md_description = "Pass - UNIX Password Manager - fuzzy search"
md_license = "MIT"
md_url = "https://github.com/bergercookie/awesome-albert-plugins"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["fuzzywuzzy"]
md_bin_dependencies = ["pass", "pass-open-doc"]
ICON_PATH = Path(__file__).parent / "pass_rlded.svg"

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
    def __init__(self, pass_dir: Path, config_path: Path):
        self.refresh = True
        self._pass_dir = pass_dir
        self._config_path = config_path

    def _save_data(self, data: str, data_name: str):
        """Save a piece of data in the configuration directory."""
        with open(self._config_path / data_name, "w") as f:
            f.write(data)

    def _load_data(self, data_name: str) -> Sequence[str]:
        """Load a piece of data from the configuration directory."""
        with open(self._config_path / data_name, "r") as f:
            return [s.strip() for s in f.readlines()]

    def _data_exists(self, data_name: str) -> bool:
        return (self._config_path / data_name).is_file()

    def _refresh_passwords(self) -> Sequence[Path]:
        passwords = tuple(self._pass_dir.rglob("**/*.gpg"))
        self._save_data("\n".join((str(p) for p in passwords)), "password_paths")

        return passwords

    def get_all_gpg_files(self) -> Sequence[Path]:
        """Get a list of all the ggp-encrypted files under the given dir."""
        passwords: Sequence[Path]
        if self.refresh is True or not self._data_exists("password_paths"):
            passwords = self._refresh_passwords()
            self.refresh = False
        else:
            passwords = tuple(Path(p) for p in self._load_data("password_paths"))

        return passwords


# plugin main functions -----------------------------------------------------------------------
def do_notify(msg: str):
    app_name = "pass_rlded"
    Notification(app_name, msg).send()


def generate_passwd_cmd(passwd_name: str) -> str:
    return f"pass generate -c -f {passwd_name}"


def generate_passwd_cmd_li(passwd_name: str) -> Sequence[str]:
    return f"pass generate -c -f {passwd_name}".split()


# supplementary functions ---------------------------------------------------------------------
def get_as_item(query, password_path: Path) -> StandardItem:
    full_path_no_suffix = Path(f"{password_path.parent}/{password_path.stem}")
    full_path_rel_root = full_path_no_suffix.relative_to(pass_dir)

    full_path_rel_root_str = str(full_path_rel_root)

    actions = [
        Action(
            "remove", "Remove", lambda a=["pass", "rm", "--force", full_path_rel_root_str]: runDetachedProcess(a)
        ),
        Action("copy", "Copy Full Path", lambda: setClipboardText(str(password_path))),
        Action("copy", "Copy Password name", lambda: setClipboardText(password_path.name)),
        Action(
            "copy", "Copy pass-compatible path", lambda: setClipboardText(full_path_rel_root_str)
        ),
    ]

    actions.insert(
        0,
        Action(
            "edit", "Edit", lambda a=["pass", "edit", full_path_rel_root_str]: runDetachedProcess(a)
        ),
    )
    actions.insert(
        0,
        Action(
            "copy",
            "Copy",
            lambda a=["pass", "--clip", full_path_rel_root_str]: runDetachedProcess(a),
        ),
    )

    if pass_open_doc_compatible(password_path):
        actions.insert(
            0,
            Action(
                "open",
                "Open document with pass-open-doc",
                lambda p=str(password_path): subprocess.run(
                    ["pass-open-doc", p], check=True
                ),
            ),
        )

    return StandardItem(
        id=f"pass-rlded-{full_path_rel_root_str}",
        icon_factory=Plugin.makeIcon,
        text=f"{password_path.stem}",
        subtext=full_path_rel_root_str,
        input_action_text=f"{query.trigger}{full_path_rel_root_str}",
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


# main plugin class ------------------------------------------------------------
class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        self.cache_path = Path(self.cacheLocation())
        self.config_path = Path(self.configLocation())
        self.data_path = Path(self.dataLocation())

        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=True, exist_ok=True)

        self.passwords_cache = PasswordsCacheManager(
            pass_dir=pass_dir, config_path=self.config_path
        )

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "pass "

    def synopsis(self, query):
        return "pass name"

    def save_data(self, data: str, data_name: str):
        """Save a piece of data in the configuration directory."""
        with open(self.config_path / data_name, "w") as f:
            f.write(data)

    def load_data(self, data_name: str) -> Sequence[str]:
        """Load a piece of data from the configuration directory."""
        with open(self.config_path / data_name, "r") as f:
            return [s.strip() for s in f.readlines()]

    def data_exists(self, data_name: str) -> bool:
        return (self.config_path / data_name).is_file()

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        results = []

        try:
            query_str = ctx.query.strip()
            if len(query_str) == 0:
                self.passwords_cache.refresh = True
                results.append(
                    StandardItem(
                        id="pass-rlded-hint",
                        icon_factory=self.makeIcon,
                        text="Continue typing to fuzzy-search on passwords...",
                        actions=[],
                    )
                )
                results.append(
                    StandardItem(
                        id="pass-rlded-generate",
                        icon_factory=self.makeIcon,
                        text="Generate a new password...",
                        input_action_text=f"{ctx.trigger}generate",
                        actions=[],
                    )
                )

            if query_str.startswith("generate"):
                if len(query_str) > 1:
                    passwd_name = " ".join(query_str.split()[1:])
                    results.insert(
                        0,
                        StandardItem(
                            id="pass-rlded-generate",
                            icon_factory=self.makeIcon,
                            text="Generate new password",
                            subtext=generate_passwd_cmd(passwd_name),
                            input_action_text=f"{ctx.trigger}{query_str}",
                            actions=[
                                Action(
                                    "generate",
                                    "Generate new password",
                                    lambda a=generate_passwd_cmd_li(
                                        passwd_name=passwd_name
                                    ): runDetachedProcess(a),
                                )
                            ],
                        ),
                    )
                else:
                    results.append(
                        StandardItem(
                            id="pass-rlded-generate",
                            icon_factory=self.makeIcon,
                            text="What's the path of this new password?",
                            subtext="e.g., awesome-e-shop/johndoe@mail.com",
                            input_action_text=f"{ctx.trigger} generate",
                            actions=[],
                        )
                    )

            # get a list of all the paths under pass_dir
            gpg_files = self.passwords_cache.get_all_gpg_files()

            # fuzzy search on the paths list
            matched = process.extract(query_str, gpg_files, limit=10)
            for m in [elem[0] for elem in matched]:
                results.append(get_as_item(ctx, m))

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)

            results.insert(
                0,
                StandardItem(
                    id="pass-rlded-error",
                    icon_factory=self.makeIcon,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        Action(
                            "copy",
                            f"Copy error - report it to {md_url[8:]}",
                            lambda: setClipboardText(str(sys.exc_info())),
                        )
                    ],
                ),
            )

        yield results
