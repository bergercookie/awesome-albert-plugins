"""Interact with Taskwarrior."""

import datetime
import os
import re
import threading
import traceback
from pathlib import Path
from shutil import which
from subprocess import PIPE, Popen
from typing import Any, Callable, List, Optional, Tuple, Union

import albert as v0  # type: ignore
import dateutil
import gi
import taskw
from fuzzywuzzy import process
from syncall import TaskWarriorSide

gi.require_version("Notify", "0.7")  # isort:skip
gi.require_version("GdkPixbuf", "2.0")  # isort:skip
from gi.repository import GdkPixbuf, Notify  # isort:skip  # type: ignore

curr_trigger: str = ""


# metadata ------------------------------------------------------------------------------------
md_name = "Taskwarrior"
md_description = "Taskwarrior - Interaction with the Taskwarrior task manager"
md_iid = "0.5"
md_version = "0.2"
md_maintainers = "Nikos Koukis"
md_url = "https://github.com/bergercookie/awesome-albert-plugins"
md_lib_dependencies = ["syncall"]
md_bin_dependencies = []

# initial checks ------------------------------------------------------------------------------

# icon ----------------------------------------------------------------------------------------
icon_path = os.path.join(os.path.dirname(__file__), "taskwarrior.svg")
icon_path_b = os.path.join(os.path.dirname(__file__), "taskwarrior_blue.svg")
icon_path_r = os.path.join(os.path.dirname(__file__), "taskwarrior_red.svg")
icon_path_y = os.path.join(os.path.dirname(__file__), "taskwarrior_yellow.svg")
icon_path_c = os.path.join(os.path.dirname(__file__), "taskwarrior_cyan.svg")
icon_path_g = os.path.join(os.path.dirname(__file__), "taskwarrior_green.svg")

# initial configuration -----------------------------------------------------------------------
failure_tag = "fail"

cache_path = Path(v0.cacheLocation()) / "taskwarrior"
config_path = Path(v0.configLocation()) / "taskwarrior"
data_path = Path(v0.dataLocation()) / "taskwarrior"

reminders_tag_path = config_path / "reminders_tag"
reminders_tag = "remindme"

# monkey-patching to solve bug in syncall - don't look.
TaskWarriorSide.get_task_id = lambda cls, item: str(item[cls.id_key()])

class FileBackedVar:
    def __init__(self, varname, convert_fn=Callable[[str], Any], init_val=None):
        self._fpath = config_path / varname
        self._convert_fn = convert_fn

        if init_val:
            with open(self._fpath, "w") as f:
                f.write(str(init_val))
        else:
            self._fpath.touch()

    def get(self) -> Any:
        with open(self._fpath, "r") as f:
            return self._convert_fn(f.read().strip())

    def set(self, val):
        with open(self._fpath, "w") as f:
            return f.write(str(val))


class TaskWarriorSideWLock:
    """Multithreading-safe version of TaskWarriorSide."""

    def __init__(self):
        self.tw = TaskWarriorSide(enable_caching=True)
        self.tw_lock = threading.Lock()

    def start(self, *args, **kargs):
        with self.tw_lock:
            return self.tw.start(*args, **kargs)

    def get_all_items(self, *args, **kargs):
        with self.tw_lock:
            return self.tw.get_all_items(*args, **kargs)

    def get_task_id(self, *args, **kargs):
        with self.tw_lock:
            return self.tw.get_task_id(*args, **kargs)

    @property
    def reload_items(self):
        return self.tw.reload_items

    @reload_items.setter
    def reload_items(self, val: bool):
        self.tw.reload_items = val

    def update_item(self, *args, **kargs):
        self.tw.update_item(*args, **kargs)


tw_side = TaskWarriorSideWLock()
last_used_date = FileBackedVar(
    "last_date_used",
    convert_fn=lambda s: datetime.datetime.strptime(s, "%Y-%m-%d").date(),
    init_val=datetime.datetime.today().date(),
)


# regular expression to match URLs
# https://gist.github.com/gruber/8891611
url_re = re.compile(
    r"""(?i)\b((?:https?:(?:/{1,3}|[a-z0-9%])|[a-z0-9.\-]+[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)/)(?:[^\s()<>{}\[\]]+|\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\))+(?:\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’])|(?:(?<!@)[a-z0-9]+(?:[.\-][a-z0-9]+)*[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\b/?(?!@)))"""
)

# plugin main functions -----------------------------------------------------------------------


def do_notify(msg: str, image=None):
    app_name = "Taskwarrior"
    Notify.init(app_name)
    image = image
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def date_only_tzlocal(datetime: datetime.datetime):
    return datetime.astimezone(dateutil.tz.tzlocal()).date()  # type: ignore


def get_tasks_of_date(date: datetime.date):
    tasks = tw_side.get_all_items(skip_completed=True)

    # You have to do the comparison in tzlocal. TaskWarrior stores the tasks in UTC and thus
    # the effetive date*time* may not match the given date parameter  because of the time
    # difference
    tasks = [t for t in tasks if "due" in t.keys() and date_only_tzlocal(t["due"]) == date]

    return tasks


def get_as_item(**kargs) -> v0.Item:
    if (urgency := kargs.get("urgency")) is not None:
        name = f"md_name_{urgency}"
        kargs.pop("urgency")
    else:
        name = md_name


    if "icon" in kargs:
        icon = kargs.pop("icon")
    else:
        icon = [icon_path]
    return v0.Item(id=name, icon=icon, **kargs)


# supplementary functions ---------------------------------------------------------------------

workers: List[threading.Thread] = []


def async_reload_items():
    def do_reload():
        v0.info("TaskWarrior: Updating list of tasks...")
        tw_side.reload_items = True
        tw_side.get_all_items(skip_completed=True)

    t = threading.Thread(target=do_reload)
    t.start()
    workers.append(t)


def setup(query):  # type: ignore
    if not which("task"):
        query.add(
            v0.Item(
                id=md_name,
                icon=[icon_path],
                text='"taskwarrior" is not installed.',
                subtext='Please install and configure "taskwarrior" accordingly.',
                actions=[
                    UrlAction(
                        'Open "taskwarrior" website', "https://taskwarrior.org/download/"
                    )
                ],
            )
        )
        return True

    return False


def save_data(data: str, data_name: str):
    """Save a piece of data in the configuration directory."""
    with open(config_path / data_name, "w") as f:
        f.write(data)


def load_data(data_name) -> str:
    """Load a piece of data from the configuration directory."""
    with open(config_path / data_name, "r") as f:
        data = f.readline().strip().split()[0]

    return data


def get_as_subtext_field(field, field_title=None):
    s = ""
    if field:
        s = f"{field} | "
    else:
        return ""

    if field_title:
        s = f"{field_title}:" + s

    return s


def urgency_to_visuals(prio: Union[float, None]) -> Tuple[Union[str, None], Path]:
    if prio is None:
        return None, Path(icon_path)
    elif prio < 4:
        return "↓", Path(icon_path_b)
    elif prio < 8:
        return "↘", Path(icon_path_c)
    elif prio < 11:
        return "-", Path(icon_path_g)
    elif prio < 15:
        return "↗", Path(icon_path_y)
    else:
        return "↑", Path(icon_path_r)


def fail_task(task_id: list):
    run_tw_action(args_list=[task_id, "modify", "+fail"])
    run_tw_action(args_list=[task_id, "done"])


def run_tw_action(args_list: list, need_pty=False):
    args_list = ["task", "rc.recurrence.confirmation=no", "rc.confirmation=off", *args_list]

    if need_pty:
        args_list.insert(0, "x-terminal-emulator")
        args_list.insert(1, "-e")

    proc = Popen(args_list, stdout=PIPE, stderr=PIPE)
    stdout, stderr = proc.communicate()

    if proc.returncode != 0:
        image = icon_path_r
        msg = f'stdout: {stdout.decode("utf-8")} | stderr: {stderr.decode("utf-8")}'
    else:
        image = icon_path
        msg = stdout.decode("utf-8")

    do_notify(msg=msg, image=image)
    async_reload_items()


def get_tw_item(task: taskw.task.Task) -> v0.Item:  # type: ignore
    """Get a single TW task as an Albert Item."""
    field = get_as_subtext_field
    task_id = tw_side.get_task_id(task)

    actions = [
        FuncAction(
            "Complete task",
            lambda args_list=["done", task_id]: run_tw_action(args_list),
        ),
        FuncAction(
            "Delete task",
            lambda args_list=["delete", task_id]: run_tw_action(args_list),
        ),
        FuncAction(
            "Start task",
            lambda args_list=["start", task_id]: run_tw_action(args_list),
        ),
        FuncAction(
            "Stop task",
            lambda args_list=["stop", task_id]: run_tw_action(args_list),
        ),
        FuncAction(
            "Edit task interactively",
            lambda args_list=["edit", task_id]: run_tw_action(args_list, need_pty=True),
        ),
        FuncAction(
            "Fail task",
            lambda task_id=task_id: fail_task(task_id=task_id),
        ),
        ClipAction("Copy task UUID", f"{task_id}"),
    ]

    found_urls = url_re.findall(task["description"])
    if "annotations" in task.keys():
        found_urls.extend(url_re.findall(" ".join(task["annotations"])))

    for url in found_urls[-1::-1]:
        actions.insert(0, UrlAction(f"Open {url}", url))

    if reminders_tag_path.is_file():
        global reminders_tag
        reminders_tag = load_data(reminders_tag_path)
    else:
        save_data("remindme", str(reminders_tag_path))

    actions.append(
        FuncAction(
            f"Add to Reminders (+{reminders_tag})",
            lambda args_list=[
                "modify",
                task_id,
                f"+{reminders_tag}",
            ]: run_tw_action(args_list),
        )
    )

    actions.append(
        FuncAction(
            "Work on next (+next)",
            lambda args_list=[
                "modify",
                task_id,
                "+next",
            ]: run_tw_action(args_list),
        )
    )

    urgency_str, icon = urgency_to_visuals(task.get("urgency"))
    text = task["description"]
    due = None
    if "due" in task:
        due = task["due"].astimezone(dateutil.tz.tzlocal()).strftime("%Y-%m-%d %H:%M:%S")  # type: ignore

    return get_as_item(
        text=text,
        subtext="{}{}{}{}{}".format(
            field(urgency_str),
            "ID: {}... | ".format(tw_side.get_task_id(task)[:8]),
            field(task["status"]),
            field(task.get("tags"), "tags"),
            field(due, "due"),
        )[:-2],
        icon=[str(icon)],
        completion=f'{curr_trigger}{task["description"]}',
        actions=actions,
        urgency=task.get("urgency"),
    )


# subcommands ---------------------------------------------------------------------------------
class Subcommand:
    def __init__(self, *, name, desc):
        self.name = name
        self.desc = desc
        self.subcommand_prefix = f"{curr_trigger}{self.name}"

    def get_as_albert_item(self, *args, **kargs):
        return get_as_item(
            text=self.desc, completion=f"{self.subcommand_prefix} ", *args, **kargs
        )

    def get_as_albert_items_full(self, query_str):
        return [self.get_as_albert_item()]

    def __str__(self) -> str:
        return f"Name: {self.name} | Description: {self.desc}"


class AddSubcommand(Subcommand):
    def __init__(self):
        super(AddSubcommand, self).__init__(name="add", desc="Add a new task")

    def get_as_albert_items_full(self, query_str):
        items = []

        subtext = query_str
        completion = f"{self.subcommand_prefix} {query_str}"
        actions = [
            FuncAction(
                "Add task",
                lambda args_list=["add", *query_str.split()]: run_tw_action(args_list),
            )
        ]
        add_item = self.get_as_albert_item(
            subtext=subtext, complection=completion, actions=actions
        )
        items.append(add_item)

        to_reminders = v0.Item(
            id=f"{md_name}_y",
            text=f"Add +{reminders_tag} tag",
            subtext="Add +remindme on [TAB]",
            icon=[icon_path_y],
            completion=f"{self.subcommand_prefix} {query_str} +remindme",
        )
        items.append(to_reminders)

        def item_at_date(date: datetime.date, time_24h: int):
            dt_str = f'{date.strftime("%Y%m%d")}T{time_24h}0000'
            return v0.Item(
                id=f"{md_name}_c",
                text=f"Due {date}, at {time_24h}:00",
                subtext="Add due:dt_str on [TAB]",
                icon=[icon_path_c],
                completion=f"{self.subcommand_prefix} {query_str} due:{dt_str}",
            )

        items.append(item_at_date(datetime.date.today(), time_24h=15))
        items.append(item_at_date(datetime.date.today(), time_24h=19))
        items.append(
            item_at_date(datetime.date.today() + datetime.timedelta(days=1), time_24h=10)
        )
        items.append(
            item_at_date(datetime.date.today() + datetime.timedelta(days=1), time_24h=15)
        )
        items.append(
            item_at_date(datetime.date.today() + datetime.timedelta(days=1), time_24h=19)
        )

        return items


class LogSubcommand(Subcommand):
    def __init__(self):
        super(LogSubcommand, self).__init__(name="log", desc="Log an already done task")

    def get_as_albert_items_full(self, query_str):
        subtext = query_str
        actions = [
            FuncAction(
                "Log task",
                lambda args_list=["log", *query_str.split()]: run_tw_action(args_list),
            )
        ]
        item = self.get_as_albert_item(subtext=subtext, actions=actions)
        return [item]


class ActiveTasks(Subcommand):
    def __init__(self):
        super(ActiveTasks, self).__init__(name="active", desc="Active tasks")

    def get_as_albert_items_full(self, query_str):
        return [
            get_tw_item(t) for t in tw_side.get_all_items(skip_completed=True) if "start" in t
        ]


def move_tasks_of_date_to_next_day(date: datetime.date):
    for t in get_tasks_of_date(date):
        tw_side.update_item(item_id=str(t["uuid"]), due=t["due"] + datetime.timedelta(days=1))


class DateTasks(Subcommand):
    """
    Common parent to classes like TodayTasks, and YesterdayTasks so as to not repeat ourselves.
    """

    def __init__(self, date: datetime.date, *args, **kargs):
        super(DateTasks, self).__init__(*args, **kargs)
        self.date = date

    def get_as_albert_item(self):
        item = super().get_as_albert_item(
            actions=[
                FuncAction(
                    "Move tasks to the day after",
                    lambda date=self.date: move_tasks_of_date_to_next_day(date),
                )
            ]
        )
        return item

    def get_as_albert_items_full(self, query_str):
        return [get_tw_item(t) for t in get_tasks_of_date(self.date)]


class TodayTasks(DateTasks):
    def __init__(self):
        super(TodayTasks, self).__init__(
            date=datetime.date.today(), name="today", desc="Today's tasks"
        )


class YesterdayTasks(DateTasks):
    def __init__(self):
        super(YesterdayTasks, self).__init__(
            date=datetime.date.today() - datetime.timedelta(days=1),
            name="yesterday",
            desc="Yesterday's tasks",
        )


class TomorrowTasks(DateTasks):
    def __init__(self):
        super(TomorrowTasks, self).__init__(
            date=datetime.date.today() + datetime.timedelta(days=1),
            name="tomorrow",
            desc="Tomorrow's tasks",
        )


class SubcommandQuery:
    def __init__(self, subcommand: Subcommand, query: str):
        """
        Query for a specific subcommand.

        :query: Query text - doesn't include the subcommand itself
        """

        self.command = subcommand
        self.query = query

    def __str__(self) -> str:
        return f"Command: {self.command}\nQuery Text: {self.query}"


def create_subcommands():
    return [
        AddSubcommand(),
        LogSubcommand(),
        ActiveTasks(),
        TodayTasks(),
        YesterdayTasks(),
        TomorrowTasks(),
    ]


subcommands = create_subcommands()


def get_subcommand_for_name(name: str) -> Optional[Subcommand]:
    """Get a subcommand with the indicated name."""
    matching = [s for s in subcommands if s.name.lower() == name.lower()]
    if matching:
        return matching[0]


def get_subcommand_query(query_str: str) -> Optional[SubcommandQuery]:
    """
    Determine whether current query is of a subcommand.

    If so first returned the corresponding SubcommandQeury object.
    """
    if not query_str:
        return None

    # spilt:
    # "subcommand_name rest of query" -> ["subcommand_name", "rest of query""]
    query_parts = query_str.strip().split(None, maxsplit=1)

    if len(query_parts) < 2:
        query_str = ""
    else:
        query_str = query_parts[1]

    subcommand = get_subcommand_for_name(query_parts[0])
    if subcommand:
        return SubcommandQuery(subcommand=subcommand, query=query_str)


# helpers for backwards compatibility ------------------------------------------
class UrlAction(v0.Action):
    def __init__(self, name: str, url: str):
        super().__init__(name, name, lambda: v0.openUrl(url))


class ClipAction(v0.Action):
    def __init__(self, name, copy_text):
        super().__init__(name, name, lambda: v0.setClipboardText(copy_text))


class FuncAction(v0.Action):
    def __init__(self, name, command):
        super().__init__(name, name, command)


# main plugin class ------------------------------------------------------------
class Plugin(v0.QueryHandler):
    def id(self) -> str:
        return __name__

    def name(self) -> str:
        return md_name

    def description(self):
        return md_description

    def defaultTrigger(self):
        return "t "

    def synopsis(self):
        return "task description"

    def finalize(self):
        pass

    def initialize(self):
        # Called when the extension is loaded (ticked in the settings) - blocking

        # create cache location
        config_path.mkdir(parents=False, exist_ok=True)

    def handleQuery(self, query) -> None:
        global curr_trigger
        curr_trigger = query.trigger

        # we're into the new day, create and assign a fresh instance
        last_used = last_used_date.get()
        current_date = datetime.datetime.today().date()

        global tw_side, subcommands
        if last_used < current_date:
            tw_side = TaskWarriorSideWLock()
            subcommands = create_subcommands()
            last_used_date.set(current_date)
        elif last_used > current_date:
            # maybe due to NTP?
            v0.critical(
                f"Current date {current_date} < last_used date {last_used} ?! Overriding"
                " current date, please report this if it persists"
            )
            tw_side = TaskWarriorSideWLock()
            subcommands = create_subcommands()
            last_used_date.set(current_date)

        results = [
            ActiveTasks().get_as_albert_item(),
            TodayTasks().get_as_albert_item(),
        ]

        # join any previously launched threads
        for i in range(len(workers)):
            workers.pop(i).join(2)

        try:
            results_setup = setup(query)
            if results_setup:
                return
            tasks = tw_side.get_all_items(skip_completed=True)

            query_str = query.string

            if len(query_str) < 2:
                results.extend([s.get_as_albert_item() for s in subcommands])
                results.append(
                    get_as_item(
                        text="Reload list of tasks",
                        actions=[FuncAction("Reload", async_reload_items)],
                    )
                )

                tasks.sort(key=lambda t: t["urgency"], reverse=True)
                results.extend([get_tw_item(task) for task in tasks])

            else:
                subcommand_query = get_subcommand_query(query_str)

                if subcommand_query:
                    results.extend(
                        subcommand_query.command.get_as_albert_items_full(
                            subcommand_query.query
                        )
                    )

                    if not results:
                        results.append(get_as_item(text="No results"))

                else:
                    # find relevant results
                    desc_to_task = {task["description"]: task for task in tasks}
                    matched = process.extract(query_str, list(desc_to_task.keys()), limit=30)
                    for m in [elem[0] for elem in matched]:
                        task = desc_to_task[m]
                        results.append(get_tw_item(task))

        except Exception:  # user to report error
            v0.critical(traceback.format_exc())

            results.insert(
                0,
                v0.Item(
                    id=md_name,
                    icon=[icon_path],
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
