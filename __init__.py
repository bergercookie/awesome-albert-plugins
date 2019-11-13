""" Interact with Taskwarrior """

from pathlib import Path
import sys
import os
from typing import Tuple

from fuzzywuzzy import process
from shutil import which
from taskw_gcal_sync import TaskWarriorSide
import albertv0 as v0
import taskw
from importlib import import_module

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


# metadata ------------------------------------------------------------------------------------
__iid__ = "PythonInterface/v0.2"
__prettyname__ = "Interact with Taskwarrior"
__version__ = "0.1.0"
__trigger__ = "t "
__author__ = "Nikos Koukis"
__dependencies__ = []
__homepage__ = "https://github.com/bergercookie/taskwarrior-albert-plugin"

# initial checks ------------------------------------------------------------------------------
if not which("task"):
    raise RuntimeError("xkcd-dl not in $PATH - Please install it via pip3 first.")

# icon ----------------------------------------------------------------------------------------
icon_path = os.path.join(os.path.dirname(__file__), "taskwarrior")
icon_path_b = os.path.join(os.path.dirname(__file__), "taskwarrior_blue")
icon_path_r = os.path.join(os.path.dirname(__file__), "taskwarrior_red")
icon_path_y = os.path.join(os.path.dirname(__file__), "taskwarrior_yellow")
icon_path_c = os.path.join(os.path.dirname(__file__), "taskwarrior_cyan")
icon_path_g = os.path.join(os.path.dirname(__file__), "taskwarrior_green")

# initial configuration -----------------------------------------------------------------------
settings_path = Path(v0.cacheLocation()) / " taskwarrior"

tw_side = TaskWarriorSide()
tw_side.start()

reminder_tag = "remindme"


def initialize():
    # Called when the extension is loaded (ticked in the settings) - blocking

    # create cache location
    settings_path.mkdir(parents=False, exist_ok=True)


def finalize():
    pass


def handleQuery(query):
    results = []

    if query.isTriggered:
        print("[__init__.py:102] DEBUGGING STRING ==> ", 0)
        if "disableSort" in dir(query):
            query.disableSort()

        try:
            tasks = tw_side.get_all_items(include_completed=False)

            if len(query.string) == 0:
                results.extend(
                    [
                        get_as_item(text=val, completion=f"{__trigger__} {key} ")
                        for key, val in zip(
                            get_prop_for_subcommands("name"), get_prop_for_subcommands("desc")
                        )
                    ]
                )

            is_subcommand, query_text = get_subcommand_query(query.string)
            if not is_subcommand:
                query_text = query.string

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
    return v0.Item(id=__prettyname__, icon=icon_path, **kargs)


# TODO - Doesn't seem to update the task.. ?
# TODO - Call python function and in there reload the items
def get_tw_item(task: taskw.task.Task) -> v0.Item:
    """Get a single TW task as an Albert Item."""
    return get_as_item(
        text=f'{task["description"]}',
        subtext="{}{}{}".format(
            "UID: {}...".format(tw_side.get_task_id(task)[:8]),
            " | status: {}".format(task["status"]),
            " | tags: {}".format(task["tags"]) if "tags" in task.keys() else "",
        ),
        completion="",
        actions=[
            v0.ProcAction(f"Add to Reminders (+{reminder_tag})", ["task", "modify",
                                                                  tw_side.get_task_id(task),
                                                                  f"+{reminder_tag}"]),
            v0.ProcAction("Complete task", ["task", "done", tw_side.get_task_id(task)]),
            v0.ProcAction("Delete task", ["task", "delete", tw_side.get_task_id(task)]),
            v0.ProcAction("Start task", ["task", "start", tw_side.get_task_id(task)]),
            v0.ProcAction("Stop task", ["task", "stop", tw_side.get_task_id(task)]),
            v0.ProcAction(
                "Edit task interactively", ["task", "edit", tw_side.get_task_id(task)]
            ),
            v0.ClipAction("Copy task UUID", f"{tw_side.get_task_id(task)}"),
        ],
    )
