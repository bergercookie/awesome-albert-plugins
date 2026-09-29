"""PulseAudio - Set I/O Audio devices and Profile."""

import traceback
from pathlib import Path
from threading import Lock
from typing import Dict, Iterator, List, Union

from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    PluginInstance,
    StandardItem,
    setClipboardText,
)
from fuzzywuzzy import process
from pulsectl import Pulse, pulsectl

md_iid = "5.0"
md_version = "0.3"
md_name = "PulseAudio - Set I/O Audio devices and profile"
md_description = "Switch between PulseAudio sources and sinks"
md_license = "BSD-2"
md_url = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins//pulse_control"
)
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["fuzzywuzzy", "pulsectl"]
pulse_lock = Lock()

src_icon_path = Path(__file__).parent / "source.svg"
sink_icon_path = Path(__file__).parent / "sink.svg"
config_icon_path = Path(__file__).parent / "configuration.svg"


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

        self.pulse = Pulse("albert-client")

    @staticmethod
    def makeIcon():
        return Icon.image(config_icon_path)

    def defaultTrigger(self):
        return "p "

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        """Handler called by albert with *every new keypress*."""
        results = []

        try:
            query_str = ctx.query.strip()

            # avoid racing conditions when multiple queries are running simultaneously (i.e,
            # current and previous query due to successive keystrokes)
            pulse_lock.acquire()
            try:
                sources_sinks: List[
                    Union[pulsectl.PulseSourceInfo, pulsectl.PulseSinkInfo]
                ] = [
                    *self.pulse.sink_list(),
                    *self.pulse.source_list(),
                ]
                cards: List[pulsectl.PulseCardInfo] = self.pulse.card_list()
            finally:
                pulse_lock.release()

            if not query_str:
                results.extend(self.render_noargs(ctx, sources_sinks, cards))
            else:
                results.extend(self.render_search(sources_sinks, cards, ctx))

        except Exception:  # user to report error
            trace = traceback.format_exc()
            print(trace)

            results.insert(
                0,
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
                ),
            )

        yield results

    def render_noargs(
        self,
        ctx,
        sources_sinks: List[Union[pulsectl.PulseSourceInfo, pulsectl.PulseSinkInfo]],
        cards: List[pulsectl.PulseCardInfo],
    ) -> List[StandardItem]:
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
                Action(
                    "set-port",
                    p.description,
                    lambda s=s, p=p: self.pulse.port_set(s, p),
                )
                for p in s.port_list
            ]

            results.append(
                StandardItem(
                    id=f"{self.id()}-port-{s.name}-{s.port_active.name}",
                    icon_factory=self._makeIcon(icon),
                    text=s.port_active.description,
                    subtext=s.description,
                    input_action_text=ctx.trigger,
                    actions=actions,
                )
            )

        # active profile for each sound card ------------------------------------------------------
        for c in cards:
            actions = [
                Action(
                    "set-profile",
                    prof.description,
                    lambda c=c, prof=prof: self.pulse.card_profile_set(c, prof),
                )
                for prof in c.profile_list
            ]

            results.append(
                StandardItem(
                    id=f"{self.id()}-profile-{c.name}-{c.profile_active.name}",
                    icon_factory=self._makeIcon(config_icon_path),
                    text=c.profile_active.description,
                    subtext=c.name,
                    input_action_text=ctx.trigger,
                    actions=actions,
                )
            )

        return results

    def render_search(
        self,
        sources_sinks: List[Union[pulsectl.PulseSourceInfo, pulsectl.PulseSinkInfo]],
        cards: List[pulsectl.PulseCardInfo],
        ctx,
    ) -> List[StandardItem]:
        results = []

        # sinks, sources
        search_str_to_props: Dict[str, list] = {
            p.description: [
                sink_icon_path if is_sink(s) else src_icon_path,
                s.description,
                lambda s=s, p=p: self.pulse.port_set(s, p),
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
                    lambda c=c, prof=prof: self.pulse.card_profile_set(c, prof),
                ]
                for c in cards
                for prof in c.profile_list
            }
        )

        # add albert items
        matched = process.extract(ctx.query, list(search_str_to_props.keys()), limit=10)
        for m in [elem[0] for elem in matched]:
            icon = search_str_to_props[m][0]
            subtext = search_str_to_props[m][1]
            action = Action("set", m, search_str_to_props[m][2])

            results.append(
                StandardItem(
                    id=f"{self.id()}-search-{m}",
                    icon_factory=self._makeIcon(icon),
                    text=m,
                    subtext=subtext,
                    input_action_text=" ".join([ctx.trigger, ctx.query]),
                    actions=[action],
                )
            )

        return results

    @staticmethod
    def _makeIcon(path):
        """Return a zero-arg icon factory for the given image path."""
        return lambda: Icon.image(path)


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
