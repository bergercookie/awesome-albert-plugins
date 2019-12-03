""" Interact with Taskwarrior """

from pathlib import Path
import sys
import os
from typing import Tuple, Union
from subprocess import call, PIPE

from fuzzywuzzy import process
from importlib import import_module
from shutil import which
from taskw_gcal_sync import TaskWarriorSide
import albertv0 as v0
import taskw

# TODO Add a subcommand for manual gcal syncing
# TODO Add a reminders tag file via dialog

# metadata ------------------------------------------------------------------------------------
__iid__ = "PythonInterface/v0.2"
__prettyname__ = "Interact with Taskwarrior"
__version__ = "0.1.0"
__trigger__ = "t "
__author__ = "Nikos Koukis"
__dependencies__ = []
__homepage__ = "https://github.com/bergercookie/taskwarrior-albert-plugin"
__simplename__ = "taskwarrior"

# initial checks ------------------------------------------------------------------------------

# icon ----------------------------------------------------------------------------------------
icon_path = os.path.join(os.path.dirname(__file__), "taskwarrior")
icon_path_b = os.path.join(os.path.dirname(__file__), "taskwarrior_blue")
icon_path_r = os.path.join(os.path.dirname(__file__), "taskwarrior_red")
icon_path_y = os.path.join(os.path.dirname(__file__), "taskwarrior_yellow")
icon_path_c = os.path.join(os.path.dirname(__file__), "taskwarrior_cyan")
icon_path_g = os.path.join(os.path.dirname(__file__), "taskwarrior_green")

# initial configuration -----------------------------------------------------------------------
cache_path = Path(v0.cacheLocation()) / __simplename__
config_path = Path(v0.configLocation()) / __simplename__
data_path = Path(v0.dataLocation()) / __simplename__

reminders_tag_path = config_path / "reminders_tag"

tw_side = TaskWarriorSide(enable_caching=True)
tw_side.start()

# plugin main functions -----------------------------------------------------------------------


def initialize():
    # Called when the extension is loaded (ticked in the settings) - blocking

    # create cache location
    config_path.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


def handleQuery(query):
    results = []

    if query.isTriggered:
        try:
            if "disableSort" in dir(query):
                query.disableSort()

            results_setup = setup(query)
            if results_setup:
                return results_setup
            tasks = tw_side.get_all_items(include_completed=False)

            # TODO Handle a potential subcommand - add?
            query_text = query.string

            if len(query.string) < 2:
                results.extend(
                    [
                        get_as_item(text=val, completion=f"{__trigger__} {key} ")
                        for key, val in zip(
                            get_prop_for_subcommands("name"), get_prop_for_subcommands("desc")
                        )
                    ]
                )

                tasks.sort(key=lambda t: t["urgency"], reverse=True)
                results.extend([get_tw_item(task) for task in tasks])

            else:
                # find relevant results
                desc_to_task = {task["description"]: task for task in tasks}
                matched = process.extract(query_text, list(desc_to_task.keys()), limit=30)
                for m in [elem[0] for elem in matched]:
                    task = desc_to_task[m]
                    results.append(get_tw_item(task))

        except Exception:  # user to report error
            results.insert(
                0,
                v0.Item(
                    id=__prettyname__,
                    icon=icon_path,
                    text="Something went wrong! Press [ENTER] to copy error and report it",
                    actions=[
                        v0.ClipAction(
                            f"Copy error - report it to {__homepage__[8:]}",
                            f"{sys.exc_info()}",
                        )
                    ],
                ),
            )

    return results


def get_as_item(**kargs) -> v0.Item:
    if "icon" in kargs:
        icon = kargs.pop("icon")
    else:
        icon = icon_path
    return v0.Item(id=__prettyname__, icon=icon, **kargs)


# supplementary functions ---------------------------------------------------------------------


def setup(query):

    results = []

    if not which("task"):
        results.append(
            v0.Item(
                id=__prettyname__,
                icon=icon_path,
                text=f'"taskwarrior" is not installed.',
                subtext='Please install and configure "taskwarrior" accordingly.',
                actions=[
                    v0.UrlAction(
                        'Open "taskwarrior" website', "https://taskwarrior.org/download/"
                    )
                ],
            )
        )
        return results

    return results


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
        return None, icon_path
    elif prio < 4:
        return "↓", icon_path_b
    elif prio < 8:
        return "↘", icon_path_c
    elif prio < 11:
        return "-", icon_path_g
    elif prio < 15:
        return "↗", icon_path_y
    else:
        return "↑", icon_path_r


def run_tw_action(args_list: list):
    args_list = ["task", "rc.recurrence.confirmation=no", "rc.confirmation=off", *args_list]
    call(args_list, stdout=PIPE, stderr=PIPE)
    tw_side.reload_items = True


def add_reminder(task_id, reminders_tag: list):
    args_list = ["modify", task_id, f"+{reminders_tag}"]
    run_tw_action(args_list)


def get_tw_item(task: taskw.task.Task) -> v0.Item:
    """Get a single TW task as an Albert Item."""
    field = get_as_subtext_field

    actions = [
        v0.FuncAction(
            "Complete task",
            lambda args_list=["done", tw_side.get_task_id(task)]: run_tw_action(args_list),
        ),
        v0.FuncAction(
            "Delete task",
            lambda args_list=["delete", tw_side.get_task_id(task)]: run_tw_action(args_list),
        ),
        v0.FuncAction(
            "Start task",
            lambda args_list=["start", tw_side.get_task_id(task)]: run_tw_action(args_list),
        ),
        v0.FuncAction(
            "Stop task",
            lambda args_list=["stop", tw_side.get_task_id(task)]: run_tw_action(args_list),
        ),
        v0.FuncAction(
            "Edit task interactively",
            lambda args_list=["edit", tw_side.get_task_id(task)]: run_tw_action(args_list),
        ),
        v0.ClipAction("Copy task UUID", f"{tw_side.get_task_id(task)}"),
    ]

    if reminders_tag_path.is_file():
        reminders_tag = load_data(reminders_tag_path)
        actions.append(
            v0.FuncAction(
                f"Add to Reminders (+{reminders_tag})",
                lambda args_list=[
                    "modify",
                    tw_side.get_task_id(task),
                    f"+{reminders_tag}",
                ]: run_tw_action(args_list),
            )
        )

    urgency_str, icon = urgency_to_visuals(task.get("urgency"))
    return get_as_item(
        text=f'{task["description"]}',
        subtext="{}{}{}{}{}".format(
            field(urgency_str),
            "ID: {}... | ".format(tw_side.get_task_id(task)[:8]),
            field(task["status"]),
            field(task.get("tags"), "tags"),
            field(task.get("due"), "due"),
        )[:-2],
        icon=icon,
        completion="",
        actions=actions,
    )


# subcommands ---------------------------------------------------------------------------------
class Subcommand:
    def __init__(self, *, name, desc, needs_existing=True):
        self.name = name
        self.desc = desc
        self.needs_existing = needs_existing


subcommands = [Subcommand(name="add", desc="Add a new task", needs_existing=False)]


def get_prop_for_subcommands(prop: str):
    """Fetch the values of the given property for all subcommands"""
    return [getattr(a, prop) for a in subcommands]


def get_subcommand_query(query_str: str) -> Tuple[bool, str]:
    """Determine whether current query is of a subcommand. If so first returned value is
    True, else False.

    If subcommand, then return the actual query excluding the subcommand else string will be
    empty

    Usage:

    >>> get_subcommand_query("add a_string")
    (True, 'a_string')
    >>> get_subcommand_query(" add another string")
    (True, 'another string')
    >>> get_subcommand_query(" adds another string")
    (False, '')
    """
    if not query_str:
        return False, ""

    query_parts = query_str.strip().split(None, maxsplit=1)
    if query_parts[0] in get_prop_for_subcommands("name"):
        return True, query_parts[1] if len(query_parts) > 1 else ""
    else:
        return False, ""
