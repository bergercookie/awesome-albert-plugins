"""Interact with the Linux bluetooth resources."""

import subprocess
import threading
import traceback
from pathlib import Path
from typing import List, Mapping, Optional, Sequence

import albert as v0
from gi.repository import GdkPixbuf, Notify

__title__ = "bluetooth"
__version__ = "0.4.0"
__triggers__ = "bl "
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/bluetooth"
)
__exec_deps__ = ["rfkill", "bluetoothctl"]

icon_path = str(Path(__file__).parent / "bluetooth0.svg")
icon_error_path = str(Path(__file__).parent / "bluetooth1.svg")

cache_path = Path(v0.cacheLocation()) / "bluetooth"
config_path = Path(v0.configLocation()) / "bluetooth"
data_path = Path(v0.dataLocation()) / "bluetooth"
dev_mode = True

workers: List[threading.Thread] = []

# create plugin locations
for p in (cache_path, config_path, data_path):
    p.mkdir(parents=False, exist_ok=True)


# BlDevice class ------------------------------------------------------------------------------
def bl_cmd(cmd: Sequence[str], check: bool = False) -> subprocess.CompletedProcess:
    """Run a bluetoothctl-wrapped command."""
    return subprocess.run(["bluetoothctl", *cmd], check=check, capture_output=True)


def async_bl_cmd(cmd: Sequence[str]):
    """
    Run a bluetoothctl-wrapped command in the background.

    Inform about the result using system nofications.
    """

    def _async_bl_cmd():
        v0.info("Running async bluetoothctl command - {cmd}")
        proc = bl_cmd(cmd=cmd)
        if proc.returncode == 0:
            notify(
                msg=f"Command {cmd} exited successfully.",
            )
        else:
            msg = f"Command {cmd} failed - " f"{proc.returncode}"
            stdout = proc.stdout.decode("utf-8").strip()
            stderr = proc.stderr.decode("utf-8").strip()
            if stdout:
                msg += f"\n\nSTDOUT:\n\n{proc.stdout}"
            if stderr:
                msg += f"\n\nSTDERR:\n\n{proc.stderr}"
            notify(msg=msg, image=icon_error_path)

    t = threading.Thread(target=_async_bl_cmd)
    t.start()
    workers.append(t)


class BlDevice:
    """Represent a single bluetooth device."""

    def __init__(self, mac_address: str, name: str):
        self.mac_address = mac_address
        self.name = name

        self.is_paired = False
        self.is_trusted = False
        self.is_blocked = False
        self.is_connected = False
        self.icon = icon_path

        try:
            d = self._parse_info()
            self.is_paired = d["Paired"] == "yes"
            self.is_trusted = d["Trusted"] == "yes"
            self.is_blocked = d["Blocked"] == "yes"
            self.is_connected = d["Connected"] == "yes"
            self.icon = d["Icon"]
        except:
            pass

    def _parse_info(self) -> Mapping[str, str]:
        proc = bl_cmd(["info", self.mac_address])
        lines = [li.decode("utf-8").strip() for li in proc.stdout.splitlines()][1:]
        return dict(li.split(": ") for li in lines)

    def trust(self) -> None:
        """Trust a device."""
        async_bl_cmd(["trust", self.mac_address])

    def pair(self) -> None:
        """Pair with a device."""
        async_bl_cmd(["pair", self.mac_address])

    def connect(self) -> None:
        """Conect to a device."""
        async_bl_cmd(["connect", self.mac_address])

    def disconnect(self) -> None:
        """Disconnect an already connected device."""
        async_bl_cmd(["disconnect", self.mac_address])


def _bl_devices_cmd(cmd: Sequence[str]) -> Sequence[BlDevice]:
    """Run a command via bluetoothct and parse assuming it returns a Device-per-line output."""
    proc = bl_cmd(cmd)
    lines = [li.decode("utf-8").strip() for li in proc.stdout.splitlines()]
    bl_devices = []
    for li in lines:
        tokens = li.strip().split()
        bl_devices.append(BlDevice(mac_address=tokens[1], name=tokens[2]))

    return bl_devices


def list_paired_devices() -> Sequence[BlDevice]:
    return _bl_devices_cmd(["paired-devices"])


def list_avail_devices() -> Sequence[BlDevice]:
    return _bl_devices_cmd(["devices"])


# plugin main functions -----------------------------------------------------------------------


def initialize():
    """Called when the extension is loaded (ticked in the settings) - blocking."""
    pass


def finalize():
    pass


def handleQuery(query) -> list:
    """Hook that is called by albert with *every new keypress*."""  # noqa
    results = []

    # join any previously launched threads
    for i in range(len(workers)):
        workers.pop(i).join(2)

    if query.isTriggered:
        try:
            query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            query_str = query.string

            # List all available device
            results.extend(get_device_as_item(dev) for dev in list_avail_devices())

            # append items to turn on / off the wifi altogether
            results.append(
                get_shell_cmd_as_item(
                    text="Enable bluetooth",
                    command="rfkill unblock bluetooth",
                )
            )
            results.append(
                get_shell_cmd_as_item(
                    text="Disable bluetooth",
                    command="rfkill block bluetooth",
                )
            )

        except Exception:  # user to report error
            v0.critical(traceback.format_exc())
            if dev_mode:  # let exceptions fly!
                raise
            else:
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


def get_device_as_item(dev: BlDevice):
    text = dev.name
    subtext = (
        f"pair: {dev.is_paired} | "
        f"connect: {dev.is_connected} | "
        f"trust: {dev.is_trusted} | "
        f"mac: {dev.mac_address}"
    )

    actions = []
    if dev.is_connected:
        actions.append(v0.FuncAction("Disconnect device", lambda dev=dev: dev.disconnect()))
    else:
        actions.append(v0.FuncAction("Connect device", lambda dev=dev: dev.connect()))
    if not dev.is_trusted:
        actions.append(v0.FuncAction("Trust device", lambda dev=dev: dev.trust()))
    if not dev.is_paired:
        actions.append(v0.FuncAction("Pair device", lambda dev=dev: dev.pair()))
    actions.append(v0.ClipAction("Copy device's MAC address", dev.mac_address))

    icon = lookup_icon(dev.icon) or icon_path
    return v0.Item(
        id=__title__,
        icon=icon,
        text=text,
        subtext=subtext,
        completion=__triggers__,
        actions=actions,
    )


def get_shell_cmd_as_item(*, text: str, command: str):
    """Return shell command as an item - ready to be appended to the items list and be rendered by Albert."""

    subtext = ""
    completion = __triggers__

    def run(command: str):
        proc = subprocess.run(command.split(" "), capture_output=True, check=False)
        if proc.returncode != 0:
            stdout = proc.stdout.decode("utf-8").strip()
            stderr = proc.stderr.decode("utf-8").strip()
            notify(
                msg=f"Error when executing {command}\n\nstdout: {stdout}\n\nstderr: {stderr}",
                image=icon_error_path,
            )

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


def lookup_icon(icon_name: str) -> Optional[str]:
    icons = list(Path(__file__).parent.glob("*.png"))

    matching = [icon for icon in icons if icon_name in icon.name]
    if matching:
        return str(matching[0])
    else:
        return None
