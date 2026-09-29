"""IPs of the host machine."""

import traceback
from pathlib import Path
from typing import Dict, Iterator, List
from urllib import request

import netifaces
from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    PluginInstance,
    StandardItem,
    setClipboardText,
)
from fuzzywuzzy import process

md_iid = "5.0"
md_version = "0.3"
md_name = "IPs of the host machine"
md_description = "Shows machine IPs"
md_license = "BSD-2"
md_url = "https://github.com/bergercookie/awesome-albert-plugins"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["fuzzywuzzy", "netifaces"]
ICON_PATH = Path(__file__).parent / "ipshow.png"

# Per-transport icons. netifaces doesn't report the interface type, so the kind is
# derived from sysfs where possible and from the interface name otherwise.
# Icons: Font Awesome Free 6 (CC BY 4.0), recoloured to a theme-neutral grey.
ICON_PATH_WIFI = Path(__file__).parent / "wifi.svg"
ICON_PATH_ETHERNET = Path(__file__).parent / "ethernet.svg"
ICON_PATH_BRIDGE = Path(__file__).parent / "bridge.svg"
ICON_PATH_LOOPBACK = Path(__file__).parent / "loopback.svg"

KIND_ICONS = {
    "wifi": ICON_PATH_WIFI,
    "ethernet": ICON_PATH_ETHERNET,
    "bridge": ICON_PATH_BRIDGE,
    "loopback": ICON_PATH_LOOPBACK,
    "unknown": ICON_PATH,
}

# netifaces gives us names only, so fall back to conventional prefixes. Note that on
# macOS a Wi-Fi link shows up as "en0", indistinguishable by name from an ethernet
# port - sysfs doesn't exist there either, so those are reported as ethernet.
KIND_NAME_PREFIXES = (
    ("loopback", ("lo", "lo0")),
    ("bridge", ("br", "br-", "bridge", "virbr")),
    ("wifi", ("wl", "wlan", "wifi", "airport")),
    ("ethernet", ("eth", "en", "enp", "eno", "ens", "em", "igb")),
)

IFF_LOOPBACK = 0x8
SYS_CLASS_NET = Path("/sys/class/net")


# flags to tweak ------------------------------------------------------------------------------
show_ipv4_only = True
discard_bridge_ifaces = True

families = netifaces.address_families


def interface_kind(iface: str) -> str:
    """Best-effort transport type of a network interface.

    Returns one of "wifi", "ethernet", "bridge", "loopback" or "unknown".
    """
    sysfs = SYS_CLASS_NET / iface
    try:
        # linux exposes the definitive answer; trust it over the name
        if (sysfs / "wireless").is_dir():
            return "wifi"
        if (sysfs / "bridge").is_dir():
            return "bridge"
        flags = int((sysfs / "flags").read_text().strip(), 0)
        if flags & IFF_LOOPBACK:
            return "loopback"
    except (OSError, ValueError):
        pass  # not linux, unreadable flags, or the interface went away

    for kind, prefixes in KIND_NAME_PREFIXES:
        if any(iface == p or iface.startswith(p) for p in prefixes):
            return kind

    return "unknown"


def filter_actions_by_query(items, query, score_cutoff=20):
    sorted_results_text = process.extractBests(
        query, [x.text for x in items], score_cutoff=score_cutoff
    )
    sorted_results_subtext = process.extractBests(
        query, [x.subtext for x in items], score_cutoff=score_cutoff
    )

    results_arr = [(x, score_cutoff) for x in items]
    for text_res, score in sorted_results_text:
        for i in range(len(items)):
            if items[i].text == text_res and results_arr[i][1] < score:
                results_arr[i] = (items[i], score)

    for subtext_res, score in sorted_results_subtext:
        for i in range(len(items)):
            if items[i].subtext == subtext_res and results_arr[i][1] < score:
                results_arr[i] = (items[i], score)

    return [x[0] for x in results_arr if x[1] > score_cutoff or len(query.strip()) == 0]


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
        return "ip "

    def synopsis(self, query):
        return "ip address or interface"

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        results = []

        if not ctx.isValid:
            return

        try:
            # External IP address -------------------------------------------------------------
            try:
                with request.urlopen("https://ipecho.net/plain", timeout=1.5) as response:
                    external_ip = response.read().decode()
            except:
                external_ip = "Timeout fetching public IP"

            results.append(
                self.get_as_item(
                    text=external_ip,
                    subtext="External IP Address",
                    actions=[
                        Action("copy", "Copy address", lambda a=external_ip: setClipboardText(a)),
                    ],
                )
            )
            # IP address in all interfaces - by default IPv4 ----------------------------------
            ifaces = netifaces.interfaces()

            # for each interface --------------------------------------------------------------
            for iface in ifaces:
                kind = interface_kind(iface)
                addrs = netifaces.ifaddresses(iface)
                for family_to_addrs in addrs.items():
                    family = families[family_to_addrs[0]]

                    # discard all but IPv4?
                    if show_ipv4_only and family != "AF_INET":
                        continue

                    # discard bridge interfaces?
                    if discard_bridge_ifaces and kind == "bridge":
                        continue

                    # for all addresses in this interface -------------------------------------
                    for i, addr_dict in enumerate(family_to_addrs[1]):
                        own_addr = addr_dict["addr"]
                        broadcast = addr_dict.get("broadcast")
                        netmask = addr_dict.get("netmask")
                        results.append(
                            self.get_as_item(
                                text=own_addr,
                                subtext=iface.ljust(15)
                                + f" | {family} | Broadcast: {broadcast} | Netmask: {netmask}",
                                icon=KIND_ICONS[kind],
                                actions=[
                                    Action("copy", "Copy address", lambda a=own_addr: setClipboardText(a)),
                                    Action("copy", "Copy interface", lambda i=iface: setClipboardText(i)),
                                ],
                            )
                        )

            # Gateways ------------------------------------------------------------------------
            # Default gateway
            def_gws: Dict[int, tuple] = netifaces.gateways()["default"]

            for def_gw in def_gws.items():
                family_int = def_gw[0]
                addr = def_gw[1][0]
                iface = def_gw[1][1]
                results.append(
                    self.get_as_item(
                        text=f"[GW - {iface}] {addr}",
                        subtext=families[family_int],
                        icon=KIND_ICONS[interface_kind(iface)],
                        actions=[
                            Action("copy", "Copy address", lambda a=addr: setClipboardText(a)),
                            Action("copy", "Copy interface", lambda i=iface: setClipboardText(i)),
                        ],
                    )
                )

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)

            results.insert(
                0,
                StandardItem(
                    id="ipshow-error",
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
        yield filter_actions_by_query(results, ctx.query, 20)

    def get_as_item(self, text, subtext, actions=[], icon=None) -> StandardItem:
        return StandardItem(
            id=f"ipshow-{text}",
            icon_factory=(
                self.makeIcon if icon is None else (lambda i=icon: Icon.image(i))
            ),
            text=text,
            subtext=subtext,
            input_action_text=self.defaultTrigger() + text,
            actions=actions,
        )


# supplementary functions ---------------------------------------------------------------------


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
