"""Interact with the Linux bluetooth resources."""

import subprocess
import threading
import traceback
from pathlib import Path
from typing import Iterator, List, Mapping, MutableMapping, Optional, Sequence

import gi

gi.require_version("Notify", "0.7")  # isort:skip
gi.require_version("GdkPixbuf", "2.0")  # isort:skip

from gi.repository import Notify  # isort:skip

from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    PluginInstance,
    StandardItem,
    setClipboardText,
)

md_iid = "5.0"
md_version = "0.3"
md_name = "Bluetooth - Connect / Disconnect bluetooth devices"
md_description = "Connect / Disconnect bluetooth devices"
md_license = "BSD-2"
md_url = "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/bluetooth"
md_maintainers = ["Nikos Koukis"]
md_bin_dependencies = ["rfkill", "bluetoothctl"]

ICON_PATH = Path(__file__).parent / "bluetooth-orig.png"
ICON_ERROR_PATH = Path(__file__).parent / "bluetooth1.svg"

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
        self.icon = d.get("Icon", str(ICON_PATH))

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


class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        # create plugin locations
        self.cache_path = Path(self.cacheLocation())
        self.config_path = Path(self.configLocation())
        self.data_path = Path(self.dataLocation())
        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "bl "

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        if not ctx.isValid:
            return

        # join any previously launched threads
        for i in range(len(workers)):
            workers.pop(i).join(2)

        try:
            results = []

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
            trace = traceback.format_exc()
            critical(trace)
            yield [
                StandardItem(
                    id=f"{self.id()}-error",
                    icon_factory=self.makeIcon,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        Action(
                            "copy",
                            f"Copy error - report it to {md_url[8:]}",
                            lambda trace=trace: setClipboardText(trace),
                        )
                    ],
                )
            ]
            return

        yield results

    def get_device_as_item(self, dev: BlDevice) -> StandardItem:
        text = dev.name
        subtext = (
            f"pair: {dev.is_paired} | "
            f"connect: {dev.is_connected} | "
            f"trust: {dev.is_trusted} | "
            f"mac: {dev.mac_address}"
        )

        actions = []
        if dev.is_connected:
            actions.append(
                Action("disconnect", "Disconnect device", lambda dev=dev: dev.disconnect())
            )
        else:
            actions.append(Action("connect", "Connect device", lambda dev=dev: dev.connect()))
        if not dev.is_trusted:
            actions.append(Action("trust", "Trust device", lambda dev=dev: dev.trust()))
        if not dev.is_paired:
            actions.append(Action("pair", "Pair device", lambda dev=dev: dev.pair()))
        actions.append(
            Action(
                "copy",
                "Copy device's MAC address",
                lambda mac=dev.mac_address: setClipboardText(mac),
            )
        )

        icon = lookup_icon(dev.icon) or ICON_PATH
        return StandardItem(
            id=f"{self.id()}-device-{dev.mac_address}",
            icon_factory=lambda icon=icon: Icon.image(icon),
            text=text,
            subtext=subtext,
            input_action_text=self.defaultTrigger(),
            actions=actions,
        )

    def get_shell_cmd_as_item(self, *, text: str, command: str) -> StandardItem:
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
                    image=str(ICON_ERROR_PATH),
                )

        return StandardItem(
            id=f"{self.id()}-cmd-{command}",
            icon_factory=self.makeIcon,
            text=text,
            subtext=subtext,
            input_action_text=completion,
            actions=[
                Action("run", text, lambda command=command: run(command=command)),
            ],
        )

    def save_data(self, data: str, data_name: str):
        """Save a piece of data in the configuration directory."""
        with open(self.config_path / data_name, "w") as f:
            f.write(data)

    def load_data(self, data_name) -> str:
        """Load a piece of data from the configuration directory."""
        with open(self.config_path / data_name, "r") as f:
            data = f.readline().strip().split()[0]

        return data


def notify(
    msg: str,
    app_name: str = md_name,
    image=str(ICON_PATH),
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
            notify(msg=msg, image=str(ICON_ERROR_PATH))

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


def lookup_icon(icon_name: str) -> Optional[Path]:
    icons = list(Path(__file__).parent.glob("*.png"))

    matching = [icon for icon in icons if icon_name in icon.name]
    if matching:
        return matching[0]
    else:
        return None
