"""Countdown/Stopwatch functionalities."""
import subprocess
import threading
import time
import traceback
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Union

import albert as v0

import gi  # isort:skip

gi.require_version("Notify", "0.7")  # isort:skip
from gi.repository import GdkPixbuf, Notify  # isort:skip

__title__ = "Countdown/Stopwatch functionalities"
__version__ = "0.4.0"
__triggers__ = "cl "
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
        t = threading.Timer(
            0.5 * x,
            lambda: subprocess.Popen(
                [
                    "cvlc",
                    sound_path,
                ]
            ),
        )
        t.start()


def notify(app_name: str, msg: str, image=None):
    if image is not None:
        image = str(image)

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
    return "▶️" if started else "⏸"


class Watch(ABC):
    def __init__(
        self,
        app_name: str,
        image_path: str,
        name: Optional[str],
        started: bool = False,
        total_time: float = 0.0,
    ):
        self._name = name if name is not None else ""
        self._to_remove = False
        self._started = started
        self._app_name = app_name
        self._image_path = image_path
        self._total_time = total_time

    def name(
        self,
    ) -> Optional[str]:
        return self._name

    def plus(self, mins: int):
        self._total_time += 60 * mins

    def minus(self, mins: int):
        self._total_time -= 60 * mins

    @abstractmethod
    def start(self):
        pass

    def started(self) -> bool:
        return self._started

    @abstractmethod
    def pause(self):
        pass

    def destroy(self):
        self.notify(msg=f"Cancelling [{self.name()}]")

    def notify(self, msg: str):
        notify(app_name=self._app_name, msg=msg, image=self._image_path)

    def to_remove(
        self,
    ) -> bool:
        return False


class Stopwatch(Watch):
    def __init__(self, name=None):
        super(Stopwatch, self).__init__(
            name=name, app_name="Stopwatch", image_path=stopwatch_path, total_time=0
        )
        self.latest_stop_time = 0
        self.latest_interval = 0
        self.start()

    def start(self):
        self.latest_start = time.time()
        self._started = True
        self.notify(msg=f"Stopwatch [{self.name()}] starting")

    def pause(self):
        stop_time = time.time()
        self.latest_interval = stop_time - self.latest_start
        self._total_time += self.latest_interval
        self._started = False
        self.notify(
            msg=f"Stopwatch [{self.name()}] paused, total: {format_time(self._total_time)}"
        )
        self.latest_stop_time = stop_time

    def __str__(self):
        # current interval
        if self.started():
            latest = time.time()
            current_interval = latest - self.latest_start
            total = self._total_time + current_interval
        else:
            latest = self.latest_stop_time
            current_interval = self.latest_interval
            total = self._total_time

        s = get_as_subtext_field(play_icon(self._started))
        s += get_as_subtext_field(self.name())
        s += get_as_subtext_field(
            format_time(total),
            "Total",
        )
        s += get_as_subtext_field(
            format_time(current_interval),
            "Current Interval",
        )[:-2]

        return s


class Countdown(Watch):
    def __init__(
        self,
        name: str,
        count_from: float,
    ):
        super(Countdown, self).__init__(
            app_name="Countdown", image_path=countdown_path, name=name, total_time=count_from
        )
        self.latest_start = 0
        self.start()

    def start(self):
        self._started = True
        self.latest_start = time.time()
        self.timer = threading.Timer(
            self._total_time,
            self.time_elapsed,
        )
        self.timer.start()
        self.notify(
            msg=f"Countdown [{self.name()}] starting, remaining: {format_time(self._total_time)}"
        )

    def pause(self):
        self._started = False
        self._total_time -= time.time() - self.latest_start
        if self.timer:
            self.timer.cancel()
            self.notify(
                msg=f"Countdown [{self.name()}] paused, remaining: {format_time(self._total_time)}"
            )

    def time_elapsed(self):
        self.notify(msg=f"Countdown [{self.name()}] finished")
        play_sound(1)
        self._to_remove = True

    def destroy(self):
        super().destroy()
        self.timer.cancel()

    def __str__(self):
        s = get_as_subtext_field(play_icon(self._started))
        s += get_as_subtext_field(self.name())

        # compute remaining time
        total_time = self._total_time
        if self.started():
            total_time -= time.time() - self.latest_start

        s += f"Remaining: {format_time(total_time)}"
        return s


all_watches: List[Watch] = []


def catch_n_notify(fn):
    def wrapper(*args, **kargs):
        try:
            fn(*args, **kargs)
        except Exception:
            notify(app_name=__title__, msg=f"Operation failed.\n\n{traceback.format_exc()}")

    return wrapper


@catch_n_notify
def create_stopwatch(name) -> None:
    all_watches.append(Stopwatch(name=name))


@catch_n_notify
def create_countdown(name: str, duration: Optional[float] = None) -> None:
    if duration is None:
        notify(app_name="Countdown", msg="No duration specified")
        return

    all_watches.append(
        Countdown(
            name=name,
            count_from=float(duration) * 60,
        )
    )


def delete_item(item: Watch):
    item.destroy()
    all_watches.remove(item)


def initialize():
    """Called when the extension is loaded (ticked in the settings) - blocking."""

    # create plugin locations
    for p in (
        cache_path,
        config_path,
        data_path,
    ):
        p.mkdir(
            parents=False,
            exist_ok=True,
        )


def finalize():
    pass


def handleQuery(
    query,
) -> list:
    """Hook that is called by albert with *every new keypress*."""  # noqa

    results = []
    if not query.string.strip() or query.isTriggered:
        results = [get_as_item(item) for item in all_watches]

    if query.isTriggered:
        try:
            query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup

            query_parts = [s.strip() for s in query.string.split()]
            name = ""
            if query_parts:
                name = query_parts[0]
                subtext_name = f"Name: {name}"
            else:
                subtext_name = "<u>Please provide a name</u>"

            # ask for duration - only applicable for countdowns
            duration = None
            if len(query_parts) > 1:
                duration = query_parts[1]
                subtext_dur = f"Duration: {duration} mins"
            else:
                subtext_dur = "<u>Please provide a duration [mins]</u>"

            results.extend(
                [
                    v0.Item(
                        id=__title__,
                        icon=countdown_path,
                        text="Create countdown",
                        subtext=f"{subtext_name} | {subtext_dur}",
                        completion=__triggers__,
                        actions=[
                            v0.FuncAction(
                                "Create countdown",
                                lambda name=name, duration=duration: create_countdown(
                                    name=name, duration=duration
                                ),
                            )
                        ],
                    ),
                    v0.Item(
                        id=__title__,
                        icon=stopwatch_path,
                        text="Create stopwatch",
                        subtext=subtext_name,
                        completion=__triggers__,
                        actions=[
                            v0.FuncAction(
                                "Create stopwatch",
                                lambda name=name: create_stopwatch(name),
                            )
                        ],
                    ),
                ]
            )

            # cleanup watches that are done
            to_remove = [watch for watch in all_watches if watch.to_remove()]
            for watch in to_remove:
                delete_item(watch)

        except Exception:  # user to report error
            v0.critical(traceback.format_exc())
            if dev_mode:  # let exceptions fly!
                raise
            else:
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


def get_as_item(item: Watch) -> v0.Item:
    """Return an item - ready to be appended to the items list and be rendered by Albert."""
    actions = []
    if item.started():
        actions.append(
            v0.FuncAction(
                "Pause",
                lambda: item.pause(),
            )
        )
    else:
        actions.append(
            v0.FuncAction(
                "Resume",
                lambda: item.start(),
            )
        )

    actions.append(
        v0.FuncAction(
            "Remove",
            lambda: delete_item(item),
        )
    )

    actions.append(
        v0.FuncAction(
            "Add 30 mins",
            lambda: item.plus(30),
        )
    )

    actions.append(
        v0.FuncAction(
            "Substract 30 mins",
            lambda: item.minus(30),
        )
    )

    actions.append(
        v0.FuncAction(
            "Add 5 mins",
            lambda: item.plus(5),
        )
    )

    actions.append(
        v0.FuncAction(
            "Substract 5 mins",
            lambda: item.minus(5),
        )
    )

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
    with open(
        config_path / data_name,
        "w",
    ) as f:
        f.write(data)


def load_data(
    data_name,
) -> str:
    """Load a piece of data from the configuration directory."""
    with open(
        config_path / data_name,
        "r",
    ) as f:
        data = f.readline().strip().split()[0]

    return data


def setup(query):
    """Setup is successful if an empty list is returned.

    Use this function if you need the user to provide you data
    """

    results = []
    return results
