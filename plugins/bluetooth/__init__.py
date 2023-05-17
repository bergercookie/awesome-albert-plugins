"""Interact with the Linux bluetooth resources."""

import subprocess
import threading
import traceback
from pathlib import Path
from typing import List, Mapping, MutableMapping, Optional, Sequence

import gi

gi.require_version("Notify", "0.7")  # isort:skip
gi.require_version("GdkPixbuf", "2.0")  # isort:skip

from gi.repository import Notify
from albert import *

md_iid = "0.5"
md_version = "0.5"
md_name = "Bluetooth - Connect / Disconnect bluetooth devices"
md_description = "Connect / Disconnect bluetooth devices"
md_license = "BSD-2"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/bluetooth"
md_maintainers = "Nikos Koukis"
md_bin_dependencies = ["rfkill", "bluetoothctl"]
icon_path = str(Path(__file__).parent / "bluetooth-orig.png")
icon_error_path = str(Path(__file__).parent / "bluetooth1.svg")

cache_path = Path(cacheLocation()) / "bluetooth"
config_path = Path(configLocation()) / "bluetooth"
data_path = Path(dataLocation()) / "bluetooth"
dev_mode = False

workers: List[threading.Thread] = []


class BlDevice:
    """Represent a single bluetooth device."""

    def __init__(self, mac_address: str, name: str):
        self.mac_address = mac_address
        self.name = name

        d = self._parse_info()
        self.is_paired = d["Paired"] == "yes"
        self.is_trusted = d["Trusted"] == "yes"
        self.is_blocked = d["Blocked"] == "yes"
        self.is_connected = d["Connected"] == "yes"
        self.icon = d.get("Icon", icon_path)

    def _parse_info(self) -> Mapping[str, str]:
        proc = bl_cmd(["info", self.mac_address])
        lines = [li.decode("utf-8").strip() for li in proc.stdout.splitlines()][1:]
        d: MutableMapping[str, str] = {}
        for li in lines:
            try:
                key, val = li.split(": ")
            except ValueError:
                # ill-formatted key
                continue

            d[key] = val

        return d

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


class ClipAction(Action):
    def __init__(self, name, copy_text):
        super().__init__(name, name, lambda: setClipboardText(copy_text))


class FuncAction(Action):
    def __init__(self, name, command):
        super().__init__(name, name, command)


class Plugin(QueryHandler):
    def id(self):
        return __name__

    def name(self):
        return md_name

    def description(self):
        return md_description

    def initialize(self):
        # create plugin locations
        for p in (cache_path, config_path, data_path):
            p.mkdir(parents=False, exist_ok=True)

    def finalize(self):
        pass

    def defaultTrigger(self):
        return "bl "

    def handleQuery(self, query):
        if not query.isValid:
            return

        results = []

        # join any previously launched threads
        for i in range(len(workers)):
            workers.pop(i).join(2)

        try:
            # List all available device
            results.extend(self.get_device_as_item(dev) for dev in list_avail_devices())

            # append items to turn on / off the wifi altogether
            results.append(
                self.get_shell_cmd_as_item(
                    text="Enable bluetooth",
                    command="rfkill unblock bluetooth",
                )
            )
            results.append(
                self.get_shell_cmd_as_item(
                    text="Disable bluetooth",
                    command="rfkill block bluetooth",
                )
            )

        except Exception:  # user to report error
            critical(traceback.format_exc())
            if dev_mode:  # let exceptions fly!
                raise
            else:
                results.insert(
                    0,
                    Item(
                        id=self.name(),
                        icon=icon_path,
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

    def get_device_as_item(self, dev: BlDevice):
        text = dev.name
        subtext = (
            f"pair: {dev.is_paired} | "
            f"connect: {dev.is_connected} | "
            f"trust: {dev.is_trusted} | "
            f"mac: {dev.mac_address}"
        )

        actions = []
        if dev.is_connected:
            actions.append(FuncAction("Disconnect device", lambda dev=dev: dev.disconnect()))
        else:
            actions.append(FuncAction("Connect device", lambda dev=dev: dev.connect()))
        if not dev.is_trusted:
            actions.append(FuncAction("Trust device", lambda dev=dev: dev.trust()))
        if not dev.is_paired:
            actions.append(FuncAction("Pair device", lambda dev=dev: dev.pair()))
        actions.append(ClipAction("Copy device's MAC address", dev.mac_address))

        icon = lookup_icon(dev.icon) or icon_path
        return Item(
            id=self.name(),
            icon=[icon],
            text=text,
            subtext=subtext,
            completion=self.defaultTrigger(),
            actions=actions,
        )

    def get_shell_cmd_as_item(self, *, text: str, command: str):
        """Return shell command as an item - ready to be appended to the items list and be rendered by Albert."""

        subtext = ""
        completion = self.defaultTrigger()

        def run(command: str):
            proc = subprocess.run(command.split(" "), capture_output=True, check=False)
            if proc.returncode != 0:
                stdout = proc.stdout.decode("utf-8").strip()
                stderr = proc.stderr.decode("utf-8").strip()
                notify(
                    msg=f"Error when executing {command}\n\nstdout: {stdout}\n\nstderr: {stderr}",
                    image=icon_error_path,
                )

        return Item(
            id=self.name(),
            icon=[icon_path],
            text=text,
            subtext=subtext,
            completion=completion,
            actions=[
                FuncAction(text, lambda command=command: run(command=command)),
            ],
        )


def notify(
    msg: str,
    app_name: str = md_name,
    image=str(icon_path),
):
    Notify.init(app_name)
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def async_bl_cmd(cmd: Sequence[str]):
    """
    Run a bluetoothctl-wrapped command in the background.

    Inform about the result using system nofications.
    """

    def _async_bl_cmd():
        info("Running async bluetoothctl command - {cmd}")
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


# BlDevice class ------------------------------------------------------------------------------
def bl_cmd(cmd: Sequence[str], check: bool = False) -> subprocess.CompletedProcess:
    """Run a bluetoothctl-wrapped command."""
    return subprocess.run(["bluetoothctl", *cmd], check=check, capture_output=True)


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


# supplementary functions ---------------------------------------------------------------------


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


def lookup_icon(icon_name: str) -> Optional[str]:
    icons = list(Path(__file__).parent.glob("*.png"))

    matching = [icon for icon in icons if icon_name in icon.name]
    if matching:
        return str(matching[0])
    else:
        return None
