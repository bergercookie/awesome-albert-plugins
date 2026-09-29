"""2FA codes using otp-cli and pass."""

import os
import subprocess
import traceback
from pathlib import Path
from typing import Iterator, List

from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    Notification,
    PluginInstance,
    StandardItem,
    setClipboardText,
)

md_iid = "5.0"
md_version = "0.3"
md_name = "OTP/2FA Codes"
md_description = "Fetch OTP codes using otp-cli and pass"
md_license = "MIT"
md_url = "https://github.com/bergercookie/awesome-albert-plugins"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["totp"]
ICON_PATH = Path(__file__).parent / "pass_totp_cli.svg"

pass_dir = Path(
    os.environ.get(
        "PASSWORD_STORE_DIR", os.path.join(os.path.expanduser("~/.password-store/"))
    )
)

pass_2fa_dir = pass_dir / "2fa"


def do_notify(msg: str):
    app_name = "pass_topt_cli"
    Notification(app_name, msg).send()


# supplementary functions ---------------------------------------------------------------------
def totp_show(name: str) -> str:
    try:
        return subprocess.check_output(["totp", "show", name]).decode("utf-8")
    except Exception:
        exc = f"Exception:\n\n{traceback.format_exc()}"
        critical(exc)
        do_notify(f"Couldn't fetch the OTP code. {exc}")
        return ""


def get_as_item(path: Path) -> StandardItem:
    name = str(path.relative_to(pass_2fa_dir).parent)
    return StandardItem(
        id=f"pass-totp-{name}",
        icon_factory=Plugin.makeIcon,
        text=name,
        input_action_text="",
        actions=[
            Action(
                "copy",
                "Copy 2FA code",
                lambda: setClipboardText(totp_show(name=name).strip()),
            )
        ],
    )


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

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "totp "

    def synopsis(self, query):
        return ""

    def save_data(self, data: str, data_name: str):
        """Save a piece of data in the configuration directory."""
        with open(self.config_path / data_name, "w") as f:
            f.write(data)

    def load_data(self, data_name) -> str:
        """Load a piece of data from the configuration directory."""
        with open(self.config_path / data_name, "r") as f:
            return f.readline().strip().split()[0]

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        results = []

        try:
            for path in pass_2fa_dir.glob("**/*.gpg"):
                results.append(get_as_item(path))

        except Exception:  # user to report error
            trace = traceback.format_exc()
            results.insert(
                0,
                StandardItem(
                    id="pass-totp-error",
                    icon_factory=self.makeIcon,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        Action(
                            "copy",
                            f"Copy error - report it to {md_url[8:]}",
                            lambda: setClipboardText(trace),
                        )
                    ],
                ),
            )

        yield results
