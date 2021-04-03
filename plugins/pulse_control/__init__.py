"""PulseAudio - Set I/O Audio devices and Profile."""

import traceback
from pathlib import Path
from threading import Lock
from typing import Dict, List, Union

from fuzzywuzzy import process
from pulsectl import Pulse, pulsectl

import albert as v0

pulse_lock = Lock()

__title__ = "PulseAudio - Set I/O Audio devices and Profile"
__version__ = "0.4.0"
__triggers__ = "p "
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins//pulse_control"
)

src_icon_path = str(Path(__file__).parent / "source")
sink_icon_path = str(Path(__file__).parent / "sink")
config_icon_path = str(Path(__file__).parent / "configuration")

cache_path = Path(v0.cacheLocation()) / "pulse_control"
config_path = Path(v0.configLocation()) / "pulse_control"
data_path = Path(v0.dataLocation()) / "pulse_control"
dev_mode = True

pulse = Pulse("albert-client")


# plugin main functions -----------------------------------------------------------------------


def initialize():
    """Called when the extension is loaded (ticked in the settings) - blocking."""

    # create plugin locations
    for p in (cache_path, config_path, data_path):
        p.mkdir(parents=False, exist_ok=True)


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

            query_str = query.string.strip()

            # avoid racing conditions when multiple queries are running simultaneously (i.e,
            # current and previous query due to successive keystrokes)
            pulse_lock.acquire()
            sources_sinks: List[Union[pulsectl.PulseSourceInfo, pulsectl.PulseSinkInfo]] = [
                *pulse.sink_list(),
                *pulse.source_list(),
            ]
            cards: List[pulsectl.PulseCardInfo] = pulse.card_list()
            pulse_lock.release()

            if not query_str:
                results.extend(render_noargs(sources_sinks, cards))
            else:
                results.extend(render_search(sources_sinks, cards, query_str))

        except Exception:  # user to report error
            if dev_mode:  # let exceptions fly!
                print(traceback.format_exc())
                raise

            results.insert(
                0,
                v0.Item(
                    id=__title__,
                    icon=None,
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


def is_sink(s):
    return isinstance(s, pulsectl.PulseSinkInfo)


def render_noargs(
    sources_sinks: List[Union[pulsectl.PulseSourceInfo, pulsectl.PulseSinkInfo]],
    cards: List[pulsectl.PulseCardInfo],
) -> List[v0.Item]:
    """Display current source, sink and card profiles."""
    results = []

    # active port for sources, sinks ----------------------------------------------------------
    for s in sources_sinks:
        # discard if it doesn't have any ports
        if s.port_active is None:
            continue

        icon = sink_icon_path if is_sink(s) else src_icon_path

        # fill actions
        actions = [
            v0.FuncAction(p.description, lambda s=s, p=p: pulse.port_set(s, p))
            for p in s.port_list
        ]

        results.append(
            v0.Item(
                id=__title__,
                icon=icon,
                text=s.port_active.description,
                subtext=s.description,
                completion=__triggers__,
                actions=actions,
            )
        )

    # active profile for each sound card ------------------------------------------------------
    for c in cards:
        actions = [
            v0.FuncAction(
                prof.description, lambda c=c, prof=prof: pulse.card_profile_set(c, prof)
            )
            for prof in c.profile_list
        ]

        results.append(
            v0.Item(
                id=__title__,
                icon=config_icon_path,
                text=c.profile_active.description,
                subtext=c.name,
                completion=__triggers__,
                actions=actions,
            )
        )

    return results


def render_search(
    sources_sinks: List[Union[pulsectl.PulseSourceInfo, pulsectl.PulseSinkInfo]],
    cards: List[pulsectl.PulseCardInfo],
    query_str: str,
) -> List[v0.Item]:
    results = []

    # sinks, sources
    search_str_to_props: Dict[str, list] = {
        p.description: [
            sink_icon_path if is_sink(s) else src_icon_path,
            s.description,
            lambda s=s, p=p: pulse.port_set(s, p),
        ]
        for s in sources_sinks
        for p in s.port_list
    }

    # profiles
    search_str_to_props.update(
        {
            prof.description: [
                config_icon_path,
                f"Profile | {c.name}",
                lambda c=c, prof=prof: pulse.card_profile_set(c, prof),
            ]
            for c in cards
            for prof in c.profile_list
        }
    )

    # add albert items
    matched = process.extract(query_str, list(search_str_to_props.keys()), limit=10)
    for m in [elem[0] for elem in matched]:
        icon = search_str_to_props[m][0]
        subtext = search_str_to_props[m][1]
        action = v0.FuncAction(m, search_str_to_props[m][2])

        results.append(
            v0.Item(
                id=__title__,
                icon=icon,
                text=m,
                subtext=subtext,
                completion=" ".join([__triggers__, query_str]),
                actions=[action],
            )
        )

    return results


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
