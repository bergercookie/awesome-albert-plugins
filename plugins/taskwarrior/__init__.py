"""Interact with Taskwarrior."""

import datetime
import os
import re
import threading
import traceback
from pathlib import Path
from shutil import which
from subprocess import PIPE, Popen
from typing import Any, Callable, Iterator, List, Optional, Tuple, Union

import dateutil
import taskw
from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    Notification,
    PluginInstance,
    StandardItem,
    openUrl,
    setClipboardText,
)
from fuzzywuzzy import process
from syncall import TaskWarriorSide

curr_trigger: str = ""


# metadata ------------------------------------------------------------------------------------
md_name = "Taskwarrior"
md_description = "Taskwarrior - Interaction with the Taskwarrior task manager"
md_iid = "5.0"
md_version = "0.3"
md_license = "MIT"
md_url = "https://github.com/bergercookie/awesome-albert-plugins"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["python-dateutil", "fuzzywuzzy", "syncall", "taskw"]
md_bin_dependencies = ["task", "x-terminal-emulator"]
# initial checks ------------------------------------------------------------------------------

# icon ----------------------------------------------------------------------------------------
ICON_PATH = Path(__file__).parent / "taskwarrior.svg"
ICON_PATH_B = Path(__file__).parent / "taskwarrior_blue.svg"
ICON_PATH_R = Path(__file__).parent / "taskwarrior_red.svg"
ICON_PATH_Y = Path(__file__).parent / "taskwarrior_yellow.svg"
ICON_PATH_C = Path(__file__).parent / "taskwarrior_cyan.svg"
ICON_PATH_G = Path(__file__).parent / "taskwarrior_green.svg"

# initial configuration -----------------------------------------------------------------------
failure_tag = "fail"

# The config location is only known on a PluginInstance; rebound in __init__.
reminders_tag_path: Path = None
reminders_tag = "remindme"

# monkey-patching to solve bug in syncall - don't look.
TaskWarriorSide.get_task_id = lambda cls, item: str(item[cls.id_key()])

class FileBackedVar:
    def __init__(self, varname, convert_fn=Callable[[str], Any], init_val=None):
        self._varname = varname
        self._fpath: Path = None
        self._convert_fn = convert_fn
        self._init_val = init_val

    def bind(self, config_dir: Path) -> "FileBackedVar":
        self._fpath = config_dir / self._varname
        self._fpath.parent.mkdir(parents=True, exist_ok=True)
        if self._init_val and not self._fpath.is_file():
            with open(self._fpath, "w") as f:
                f.write(str(self._init_val))
        elif not self._fpath.is_file():
            self._fpath.touch()
        return self

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


def do_notify(msg: str):
    app_name = "Taskwarrior"
    Notification(app_name, msg).send()


def date_only_tzlocal(datetime: datetime.datetime):
    return datetime.astimezone(dateutil.tz.tzlocal()).date()  # type: ignore


def get_tasks_of_date(date: datetime.date):
    tasks = tw_side.get_all_items(skip_completed=True)

    # You have to do the comparison in tzlocal. TaskWarrior stores the tasks in UTC and thus
    # the effetive date*time* may not match the given date parameter  because of the time
    # difference
    tasks = [t for t in tasks if "due" in t.keys() and date_only_tzlocal(t["due"]) == date]

    return tasks


def get_as_item(**kargs) -> StandardItem:
    if (urgency := kargs.get("urgency")) is not None:
        kargs.pop("urgency")
        name = f"{md_name}_{urgency}"
    else:
        name = md_name

    if "icon" in kargs:
        icon = kargs.pop("icon")
        if isinstance(icon, (list, tuple)):
            icon = icon[0]
    else:
        icon = ICON_PATH
    if "completion" in kargs:
        kargs["input_action_text"] = kargs.pop("completion")
    # item ids drive de-duplication - derive a stable one when not given
    kargs.setdefault("id", f"{name}-{kargs.get('text', '')}")
    return StandardItem(icon_factory=lambda: Icon.image(icon), **kargs)


# supplementary functions ---------------------------------------------------------------------

workers: List[threading.Thread] = []


def async_reload_items():
    def do_reload():
        info("TaskWarrior: Updating list of tasks...")
        tw_side.reload_items = True
        tw_side.get_all_items(skip_completed=True)

    t = threading.Thread(target=do_reload)
    t.start()
    workers.append(t)


def setup() -> Optional[List[StandardItem]]:
    """Return a list of items if setup is required, else None."""
    if not which("task"):
        return [
            StandardItem(
                id=f"{md_name}-not-installed",
                icon_factory=lambda: Icon.image(ICON_PATH),
                text='"taskwarrior" is not installed.',
                subtext='Please install and configure "taskwarrior" accordingly.',
                actions=[
                    Action(
                        "open",
                        'Open "taskwarrior" website',
                        lambda: openUrl("https://taskwarrior.org/download/"),
                    )
                ],
            )
        ]

    return None


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
        return None, ICON_PATH
    elif prio < 4:
        return "↓", ICON_PATH_B
    elif prio < 8:
        return "↘", ICON_PATH_C
    elif prio < 11:
        return "-", ICON_PATH_G
    elif prio < 15:
        return "↗", ICON_PATH_Y
    else:
        return "↑", ICON_PATH_R


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
        msg = f'stdout: {stdout.decode("utf-8")} | stderr: {stderr.decode("utf-8")}'
    else:
        msg = stdout.decode("utf-8")

    do_notify(msg=msg)
    async_reload_items()


def get_tw_item(task: taskw.task.Task) -> StandardItem:  # type: ignore
    """Get a single TW task as an Albert Item."""
    field = get_as_subtext_field
    task_id = tw_side.get_task_id(task)

    actions = [
        Action(
            "complete",
            "Complete task",
            lambda args_list=["done", task_id]: run_tw_action(args_list),
        ),
        Action(
            "delete",
            "Delete task",
            lambda args_list=["delete", task_id]: run_tw_action(args_list),
        ),
        Action(
            "start",
            "Start task",
            lambda args_list=["start", task_id]: run_tw_action(args_list),
        ),
        Action(
            "stop",
            "Stop task",
            lambda args_list=["stop", task_id]: run_tw_action(args_list),
        ),
        Action(
            "edit",
            "Edit task interactively",
            lambda args_list=["edit", task_id]: run_tw_action(args_list, need_pty=True),
        ),
        Action(
            "fail",
            "Fail task",
            lambda task_id=task_id: fail_task(task_id=task_id),
        ),
        Action("copy", "Copy task UUID", lambda: setClipboardText(f"{task_id}")),
    ]

    found_urls = url_re.findall(task["description"])
    if "annotations" in task.keys():
        found_urls.extend(url_re.findall(" ".join(task["annotations"])))

    for url in found_urls[-1::-1]:
        actions.insert(0, Action("open", f"Open {url}", lambda u=url: openUrl(u)))

    if reminders_tag_path.is_file():
        global reminders_tag
        with open(reminders_tag_path, "r") as f:
            reminders_tag = f.readline().strip().split()[0]
    else:
        with open(reminders_tag_path, "w") as f:
            f.write(reminders_tag)

    actions.append(
        Action(
            "remind",
            f"Add to Reminders (+{reminders_tag})",
            lambda args_list=[
                "modify",
                task_id,
                f"+{reminders_tag}",
            ]: run_tw_action(args_list),
        )
    )

    actions.append(
        Action(
            "next",
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
        input_action_text=f'{curr_trigger}{task["description"]}',
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
            text=self.desc, input_action_text=f"{self.subcommand_prefix} ", *args, **kargs
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
        actions = [
            Action(
                "add",
                "Add task",
                lambda args_list=["add", *query_str.split()]: run_tw_action(args_list),
            )
        ]
        add_item = self.get_as_albert_item(
            subtext=subtext,
            input_action_text=f"{self.subcommand_prefix} {query_str}",
            actions=actions,
        )
        items.append(add_item)

        to_reminders = StandardItem(
            id=f"{md_name}-reminders",
            text=f"Add +{reminders_tag} tag",
            subtext="Add +remindme on [TAB]",
            icon_factory=lambda: Icon.image(ICON_PATH_Y),
            input_action_text=f"{self.subcommand_prefix} {query_str} +remindme",
        )
        items.append(to_reminders)

        def item_at_date(date: datetime.date, time_24h: int):
            dt_str = f'{date.strftime("%Y%m%d")}T{time_24h}0000'
            return StandardItem(
                id=f"{md_name}-due-{dt_str}",
                text=f"Due {date}, at {time_24h}:00",
                subtext="Add due:dt_str on [TAB]",
                icon_factory=lambda: Icon.image(ICON_PATH_C),
                input_action_text=f"{self.subcommand_prefix} {query_str} due:{dt_str}",
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
            Action(
                "log",
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
                Action(
                    "move",
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


# main plugin class ------------------------------------------------------------
class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        self.cache_path = Path(self.cacheLocation())
        self.config_path = Path(self.configLocation())
        self.data_path = Path(self.dataLocation())

        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=True, exist_ok=True)

        global reminders_tag_path
        reminders_tag_path = self.config_path / "reminders_tag"
        last_used_date.bind(self.config_path)

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "t "

    def synopsis(self, query):
        return "task description"

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        """Yield the task items for the current query."""
        global curr_trigger
        curr_trigger = ctx.trigger

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
            critical(
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
            results_setup = setup()
            if results_setup:
                yield results_setup
                return
            tasks = tw_side.get_all_items(skip_completed=True)

            query_str = ctx.query

            if len(query_str) < 2:
                results.extend([s.get_as_albert_item() for s in subcommands])
                results.append(
                    get_as_item(
                        text="Reload list of tasks",
                        actions=[Action("reload", "Reload", async_reload_items)],
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
            trace = traceback.format_exc()
            critical(trace)

            results.insert(
                0,
                StandardItem(
                    id=f"{md_name}-error",
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

        yield results
