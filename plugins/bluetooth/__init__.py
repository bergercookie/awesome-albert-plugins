"""Interact with the Linux bluetooth resources."""

from pathlib import Path
import subprocess
import traceback

from gi.repository import GdkPixbuf, Notify

import albert as v0

__title__ = "bluetooth"
__version__ = "0.4.0"
__triggers__ = "bl "
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/bluetooth"
)
__exec_deps__ = ["rfkill"]
__py_deps__ = []

icon_path = str(Path(__file__).parent / "bluetooth.png")

cache_path = Path(v0.cacheLocation()) / "bluetooth"
config_path = Path(v0.configLocation()) / "bluetooth"
data_path = Path(v0.dataLocation()) / "bluetooth"
dev_mode = True

# create plugin locations
for p in (cache_path, config_path, data_path):
    p.mkdir(parents=False, exist_ok=True)

# plugin main functions -----------------------------------------------------------------------


def initialize():
    """Called when the extension is loaded (ticked in the settings) - blocking."""
    pass


def finalize():
    pass


def handleQuery(query) -> list:
    """Hook that is called by albert with *every new keypress*."""  # noqa
    results = []

    if query.isTriggered:
        try:
            query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            query_str = query.string
            results.append(
                get_shell_cmd_as_item(
                    text="enable",
                    command="rfkill unblock bluetooth",
                    subtext="Enable bluetooth",
                )
            )
            results.append(
                get_shell_cmd_as_item(
                    text="disable",
                    command="rfkill block bluetooth",
                    subtext="Disable bluetooth",
                )
            )

        except Exception:  # user to report error
            if dev_mode:  # let exceptions fly!
                v0.critical(traceback.format_exc())
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
                            f"{traceback.format_exc()}",
                        )
                    ],
                ),
            )

    return results


# supplementary functions ---------------------------------------------------------------------
def notify(
    msg: str,
    app_name: str = __title__,
    image=str(icon_path),
):
    Notify.init(app_name)
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def get_shell_cmd_as_item(
    *, text: str, command: str, subtext: str = None, completion: str = None
):
    """Return shell command as an item - ready to be appended to the items list and be rendered by Albert."""

    if subtext is None:
        subtext = text

    if completion is None:
        completion = f"{__triggers__}{text}"

    def run(command: str):
        proc = subprocess.run(command.split(" "), capture_output=True, check=False)
        if proc.returncode != 0:
            stdout = proc.stdout.decode("utf-8")
            stderr = proc.stderr.decode("utf-8")
            notify(f"Error when executing {command}\n\nstdout: {stdout}\n\nstderr: {stderr}")

    return v0.Item(
        id=__title__,
        icon=icon_path,
        text=text,
        subtext=subtext,
        completion=completion,
        actions=[
            v0.FuncAction(text, lambda command=command: run(command=command)),
        ],
    )


def sanitize_string(s: str) -> str:
    return s.replace("<", "&lt;")


def get_as_subtext_field(field, field_title=None) -> str:
    """Get a certain variable as part of the subtext, along with a title for that variable."""
    s = ""
    if field:
        s = f"{field} | "
    else:
        return ""

    if field_title:
        s = f"{field_title}: " + s

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
    """Setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []
    return results
