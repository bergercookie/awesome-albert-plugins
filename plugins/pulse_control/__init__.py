"""PulseAudio - Set I/O Audio devices and Profile."""

import traceback
from pathlib import Path
from threading import Lock
from typing import Dict, List, Union

from fuzzywuzzy import process
from pulsectl import Pulse, pulsectl


from albert import *

md_iid = "0.5"
md_version = "0.2"
md_name = "PulseAudio - Set I/O Audio devices and profile"
md_description = "Switch between PulseAudio sources and sinks"
md_license = "BSD-2"
md_url = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins//pulse_control"
)
md_maintainers = "Nikos Koukis"
md_lib_dependencies = ["pulsectl"]


pulse_lock = Lock()

src_icon_path = str(Path(__file__).parent / "source")
sink_icon_path = str(Path(__file__).parent / "sink")
config_icon_path = str(Path(__file__).parent / "configuration")

cache_path = Path(cacheLocation()) / "pulse_control"
config_path = Path(configLocation()) / "pulse_control"
data_path = Path(dataLocation()) / "pulse_control"

pulse = Pulse("albert-client")


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

    def defaultTrigger(self):
        return "p "

    def initialize(self):
        """Called when the extension is loaded (ticked in the settings) - blocking."""

        # create plugin locations
        for p in (cache_path, config_path, data_path):
            p.mkdir(parents=False, exist_ok=True)

    def finalize(self):
        pass

    def handleQuery(self, query) -> list:
        """Hook that is called by albert with *every new keypress*."""  # noqa
        results = []

        try:
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
                results.extend(self.render_noargs(query, sources_sinks, cards))
            else:
                results.extend(self.render_search(sources_sinks, cards, query))

        except Exception:  # user to report error
            if dev_mode:  # let exceptions fly!
                print(traceback.format_exc())
                raise

            results.insert(
                0,
                Item(
                    id=self.name(),
                    icon=[],
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

    def render_noargs(
        self,
        query,
        sources_sinks: List[Union[pulsectl.PulseSourceInfo, pulsectl.PulseSinkInfo]],
        cards: List[pulsectl.PulseCardInfo],
    ) -> List[Item]:
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
                FuncAction(p.description, lambda s=s, p=p: pulse.port_set(s, p))
                for p in s.port_list
            ]

            results.append(
                Item(
                    id=self.name(),
                    icon=[icon],
                    text=s.port_active.description,
                    subtext=s.description,
                    completion=query.trigger,
                    actions=actions,
                )
            )

        # active profile for each sound card ------------------------------------------------------
        for c in cards:
            actions = [
                FuncAction(
                    prof.description, lambda c=c, prof=prof: pulse.card_profile_set(c, prof)
                )
                for prof in c.profile_list
            ]

            results.append(
                Item(
                    id=self.name(),
                    icon=[config_icon_path],
                    text=c.profile_active.description,
                    subtext=c.name,
                    completion=query.trigger,
                    actions=actions,
                )
            )

        return results

    def render_search(
        self,
        sources_sinks: List[Union[pulsectl.PulseSourceInfo, pulsectl.PulseSinkInfo]],
        cards: List[pulsectl.PulseCardInfo],
        query,
    ) -> List[Item]:
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
        matched = process.extract(query.string, list(search_str_to_props.keys()), limit=10)
        for m in [elem[0] for elem in matched]:
            icon = search_str_to_props[m][0]
            subtext = search_str_to_props[m][1]
            action = FuncAction(m, search_str_to_props[m][2])

            results.append(
                Item(
                    id=self.name(),
                    icon=[icon],
                    text=m,
                    subtext=subtext,
                    completion=" ".join([query.trigger, query.string]),
                    actions=[action],
                )
            )

        return results


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


def is_sink(s):
    return isinstance(s, pulsectl.PulseSinkInfo)
