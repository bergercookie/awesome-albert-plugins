"""Countdown/Stopwatch functionalities."""
import subprocess
import threading
import time
import traceback
from abc import (
    ABC,
    abstractmethod,
)
from pathlib import Path
from typing import (
    List,
    Optional,
    Union,
)

from overrides import overrides

import albert as v0

import gi # isort:skip
gi.require_version("Notify", "0.7")  # isort:skip
from gi.repository import (
    GdkPixbuf,
    Notify,
)  # isort:skip


__title__ = "Countdown/Stopwatch functionalities"
__version__ = "0.4.0"
__triggers__ = "clock "
__authors__ = "Nikos Koukis"
__homepage__ = (
    "https://github.com/bergercookie/awesome-albert-plugins/blob/master/plugins/clock"
)

countdown_path = str(Path(__file__).parent / "countdown.png")
stopwatch_path = str(Path(__file__).parent / "stopwatch.png")
sound_path = Path(__file__).parent.absolute() / "bing.wav"

cache_path = Path(v0.cacheLocation()) / "clock"
config_path = Path(v0.configLocation()) / "clock"
data_path = Path(v0.dataLocation()) / "clock"
dev_mode = True

# plugin main functions -----------------------------------------------------------------------


def play_sound(num):
    for x in range(num):
        t = threading.Timer(0.5 * x, lambda: subprocess.Popen(["cvlc", sound_path,]),)
        t.start()


def notify(
    app_name: str, msg: str, image=None,
):
    Notify.init(app_name)
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def format_time(t: float):
    """Return the string representation of t. t must be in *seconds*"""
    if t >= 60:
        return f"{round(t / 60.0, 2)} mins"
    else:
        return f"{round(t, 2)} secs"


def play_icon(started) -> str:
    return "▶️" if started else "⏸️"


class Watch(ABC):
    def __init__(self, name):
        self._name = name if name is not None else ""
        self._to_remove = False

    def name(self,) -> Optional[str]:
        return self._name

    @abstractmethod
    def start(self):
        pass

    def started(self) -> bool:
        pass
        return self._started

    @abstractmethod
    def pause(self):
        pass

    @abstractmethod
    def notify(self):
        pass

    def to_remove(self,) -> bool:
        return False


class Stopwatch(Watch):
    def __init__(self, name=None):
        super(Stopwatch, self).__init__(name=name)
        self.total_time = 0
        self.latest_start = 0
        self._started = False
        self.latest_stop_time = 0

    @overrides
    def start(self):
        self.latest_start = time.time()
        self._started = True
        self.notify(msg=f"Stopwatch [{self.name()}] starting")

    @overrides
    def pause(self):
        stop_time = time.time()
        self.total_time += stop_time - self.latest_start
        self._started = False
        self.notify(
            msg=f"Stopwatch [{self.name()}] paused, total: {format_time(self.total_time)}"
        )
        self.latest_stop_time = stop_time

    @overrides
    def notify(self, msg):
        notify(
            app_name="Stopwatch", msg=msg, image=stopwatch_path,
        )

    @classmethod
    def icon(cls):
        return stopwatch_path

    def destroy(self):
        pass

    def __str__(self):
        # current interval
        if self.started():
            latest = time.time()
        else:
            latest = self.latest_stop_time
        current_interval = latest - self.latest_start
        total = self.total_time + current_interval
        s = get_as_subtext_field(play_icon(self._started))
        s += get_as_subtext_field(self.name())
        s += get_as_subtext_field(format_time(total), "Total",)
        s += get_as_subtext_field(format_time(current_interval), "Current Interval",)[:-2]

        return s


class Countdown(Watch):
    def __init__(
        self, name: str, count_from: float,
    ):
        super(Countdown, self).__init__(name=name)
        self.latest_start = 0
        self.remaining_time = count_from
        self._started = False
        self.timer = None

    @overrides
    def start(self):
        self._started = True
        self.latest_start = time.time()
        self.timer = threading.Timer(self.remaining_time, self.time_elapsed,)
        self.timer.start()
        self.notify(
            msg=f"Countdown [{self.name()}] starting, remaining: {format_time(self.remaining_time)}"
        )

    @overrides
    def pause(self):
        self._started = False
        self.remaining_time -= time.time() - self.latest_start
        if self.timer:
            self.timer.cancel()
            self.notify(
                msg=f"Countdown [{self.name()}] paused, remaining: {format_time(self.remaining_time)}"
            )

    def time_elapsed(self):
        self.notify(msg=f"Countdown [{self.name()}] finished")
        play_sound(1)
        self._to_remove = True

    @classmethod
    def icon(cls):
        return countdown_path

    def destroy(self):
        self.timer.cancel()
        self.notify(msg=f"Cancelling [{self.name()}]")

    @overrides
    def notify(self, msg):
        notify(
            app_name="Countdown", msg=msg, image=countdown_path,
        )

    def __str__(self):
        s = get_as_subtext_field(play_icon(self._started))
        s += get_as_subtext_field(self.name())

        # compute remaining time
        remaining_time = self.remaining_time
        if self.started():
            remaining_time -= time.time() - self.latest_start

        s += f"Remaining: {format_time(remaining_time)}"
        return s


countdowns: List[Countdown] = []
stopwatches: List[Stopwatch] = []


def all_watches() -> List[Union[Countdown, Stopwatch]]:
    return [
        *countdowns,
        *stopwatches,
    ]


def create_stopwatch(name, *query_parts):
    stopwatches.append(Stopwatch(name=name))
    stopwatches[-1].start()


def create_countdown(name, *query_parts):
    t = float(query_parts[0].strip()) * 60

    countdowns.append(Countdown(name=name, count_from=t,))
    countdowns[-1].start()


def delete_item(item: Union[Stopwatch, Countdown]):
    item.destroy()

    # TODO: could be neater..
    if isinstance(item, Stopwatch):
        stopwatches.remove(item)
    else:
        countdowns.remove(item)


def initialize():
    """Called when the extension is loaded (ticked in the settings) - blocking."""

    # create plugin locations
    for p in (
        cache_path,
        config_path,
        data_path,
    ):
        p.mkdir(
            parents=False, exist_ok=True,
        )


def finalize():
    pass


def handleQuery(query,) -> list:
    """Hook that is called by albert with *every new keypress*."""  # noqa
    results = []

    if query.isTriggered:
        try:
            query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            query_parts = query.string.strip().split()
            name = None
            if query_parts:
                name = query_parts.pop(0)
            subtext = f'Name: {name if name else "Not given"}'

            results.extend(
                [
                    v0.Item(
                        id=__title__,
                        icon=countdown_path,
                        text="Create countdown",
                        subtext=f'{subtext}{" - <u>Please provide a duration</u>" if not query_parts else ""}',
                        completion=__triggers__,
                        actions=[
                            v0.FuncAction(
                                "Create countdown",
                                lambda name=name, query_parts=query_parts: create_countdown(
                                    name, *query_parts,
                                ),
                            )
                        ],
                    ),
                    v0.Item(
                        id=__title__,
                        icon=stopwatch_path,
                        text="Create stopwatch",
                        subtext=subtext,
                        completion=__triggers__,
                        actions=[
                            v0.FuncAction(
                                "Create stopwatch",
                                lambda name=name, query_parts=query_parts: create_stopwatch(
                                    name, *query_parts,
                                ),
                            )
                        ],
                    ),
                ]
            )

            # cleanup watches that are done
            for li in [
                countdowns,
                stopwatches,
            ]:
                for watch in li:
                    if watch.to_remove():
                        li.remove(watch)

            results.extend([get_as_item(item) for item in all_watches()])

        except Exception:  # user to report error
            if dev_mode:  # let exceptions fly!
                print(traceback.format_exc())
                raise

            results.insert(
                0,
                v0.Item(
                    id=__title__,
                    icon=countdown_path,
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


def get_as_item(item: Union[Countdown, Stopwatch]):
    """Return an item - ready to be appended to the items list and be rendered by Albert."""
    actions = [v0.FuncAction("Remove", lambda: delete_item(item),)]
    if item.started():
        actions.append(v0.FuncAction("Pause", lambda: item.pause(),))
    else:
        actions.append(v0.FuncAction("Resume", lambda: item.start(),))

    return v0.Item(
        id=__title__,
        icon=countdown_path if isinstance(item, Countdown) else stopwatch_path,
        text=str(item),
        subtext="",
        completion=__triggers__,
        actions=actions,
    )


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
    with open(config_path / data_name, "w",) as f:
        f.write(data)


def load_data(data_name,) -> str:
    """Load a piece of data from the configuration directory."""
    with open(config_path / data_name, "r",) as f:
        data = f.readline().strip().split()[0]

    return data


def setup(query):
    """Setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []
    return results
