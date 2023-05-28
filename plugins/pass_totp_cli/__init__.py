"""2FA codes using otp-cli and pass."""

import os
import subprocess
import traceback
from pathlib import Path

import albert as v0
import gi

gi.require_version("Notify", "0.7")  # isort:skip
gi.require_version("GdkPixbuf", "2.0")  # isort:skip
from gi.repository import GdkPixbuf, Notify  # isort:skip  # type: ignore

md_name = "OTP/2FA Codes"
md_description = "Fetch OTP codes using otp-cli and pass"
md_iid = "0.5"
md_version = "0.2"
md_maintainers = "Nikos Koukis"
md_url = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/pass_totp_cli"
)
md_bin_dependencies = ["pass", "totp"]

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


def do_notify(msg: str, image=None):
    app_name = "pass_topt_cli"
    Notify.init(app_name)
    image = image
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


# supplementary functions ---------------------------------------------------------------------
def totp_show(name: str) -> str:
    try:
        return subprocess.check_output(["totp", "show", name]).decode("utf-8")
    except Exception:
        exc = f"Exception:\n\n{traceback.format_exc()}"
        v0.critical(exc)
        do_notify(f"Couldn't fetch the OTP code. {exc}")
        return ""


def get_as_item(path: Path):
    name = str(path.relative_to(pass_2fa_dir).parent)
    return v0.Item(
        id=md_name,
        icon=[icon_path],
        text=name,
        completion="",
        actions=[
            FuncAction(
                "Copy 2FA code",
                lambda name=name: totp_show(name=name).strip(),
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


# main plugin class ------------------------------------------------------------
class Plugin(v0.QueryHandler):
    def id(self) -> str:
        return __name__

    def name(self) -> str:
        return md_name

    def description(self):
        return md_description

    def defaultTrigger(self):
        return "totp "

    def synopsis(self):
        return ""

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
            for path in pass_2fa_dir.glob("**/*.gpg"):
                results.append(get_as_item(path))

        except Exception:  # user to report error
            results.insert(
                0,
                v0.Item(
                    id=md_name,
                    icon=[icon_path],
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        ClipAction(
                            f"Copy error - report it to {md_url[8:]}",
                            f"{traceback.format_exc()}",
                        )
                    ],
                ),
            )

        query.add(results)
