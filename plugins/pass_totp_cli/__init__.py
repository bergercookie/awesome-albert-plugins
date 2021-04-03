"""2FA codes using otp-cli and pass."""

import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Dict, Tuple

from fuzzywuzzy import process

import albert as v0

__title__ = "Fetch OTP codes using otp-cli and pass"
__version__ = "0.4.0"
__triggers__ = "totp"
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/pass_totp_cli"
)

icon_path = str(Path(__file__).parent / "pass_totp_cli")

cache_path = Path(v0.cacheLocation()) / "pass_totp_cli"
config_path = Path(v0.configLocation()) / "pass_totp_cli"
data_path = Path(v0.dataLocation()) / "pass_totp_cli"

pass_dir = Path(
    os.environ.get(
        "PASSWORD_STORE_DIR", os.path.join(os.path.expanduser("~/.password-store/"))
    )
)

pass_2fa_dir = pass_dir / "2fa"

# plugin main functions -----------------------------------------------------------------------


def initialize():
    # Called when the extension is loaded (ticked in the settings) - blocking

    # create plugin locations
    for p in (cache_path, config_path, data_path):
        p.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


def handleQuery(query) -> list:
    results = []

    if query.isTriggered:
        try:
            # be backwards compatible with v0.2
            if "disableSort" in dir(query):
                query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            for path in pass_2fa_dir.iterdir():
                results.append(get_as_item(path))

        except Exception:  # user to report error
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


def get_as_item(path: Path):
    return v0.Item(
        id=__title__,
        icon=icon_path,
        text=path.stem,
        completion="",
        actions=[
            v0.FuncAction(
                "Copy 2FA code",
                lambda name=path.stem: subprocess.check_output(["totp", "show", name]).strip(),
            )
        ],
    )


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
