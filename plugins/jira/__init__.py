""" Jira Issue Tracking."""

import os
import shutil
import subprocess
import traceback
from pathlib import Path
from typing import cast

from fuzzywuzzy import process
from jira import JIRA, resources
from jira.client import ResultList

import albert as v0

# initial configuration -----------------------------------------------------------------------

md_name = "Jira"
md_description = "Jira Issue Tracking"
md_iid = "0.5"
md_version = "0.2"
md_maintainers = "Nikos Koukis"
md_url = "https://github.com/bergercookie/jira-albert-plugin"
__simplename__ = "jira"
md_bin_dependenciesa = []

icon_path = os.path.join(os.path.dirname(__file__), "jira_blue")
icon_path_br = os.path.join(os.path.dirname(__file__), "jira_bold_red")
icon_path_r = os.path.join(os.path.dirname(__file__), "jira_red")
icon_path_y = os.path.join(os.path.dirname(__file__), "jira_yellow")
icon_path_g = os.path.join(os.path.dirname(__file__), "jira_green")
icon_path_lg = os.path.join(os.path.dirname(__file__), "jira_light_green")

# plugin locations
cache_path = Path(v0.cacheLocation()) / __simplename__
config_path = Path(v0.configLocation()) / __simplename__
data_path = Path(v0.dataLocation()) / __simplename__

pass_path = Path().home() / ".password-store"
user_path = config_path / "user"
server_path = config_path / "server"
api_key_path = pass_path / "jira-albert-plugin" / "api-key.gpg"

max_results_to_request = 50
max_results_to_show = 5
fields_to_include = ["assignee", "issuetype", "priority", "project", "status", "summary"]

prio_to_icon = {
    "Highest": icon_path_br,
    "High": icon_path_r,
    "Medium": icon_path_y,
    "Low": icon_path_g,
    "Lowest": icon_path_lg,
}

prio_to_text = {"Highest": "↑", "High": "↗", "Medium": "-", "Low": "↘", "Lowest": "↓"}

# supplementary functions ---------------------------------------------------------------------


def get_create_issue_page(server: str) -> str:
    return server + "/secure/CreateIssue!default.jspa"


def save_data(data: str, data_name: str):
    """Save a piece of data in the configuration directory."""
    with open(config_path / data_name, "w") as f:
        f.write(data)


def load_data(data_name) -> str:
    """Load a piece of data from the configuration directory."""
    with open(config_path / data_name, "r") as f:
        data = f.readline().strip().split()[0]

    return data


def load_api_key() -> str:
    try:
        ret = subprocess.run(
            ["gpg", "--decrypt", api_key_path],
            timeout=2,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        api_key = ret.stdout.decode("utf-8").strip()
        return api_key

    except subprocess.TimeoutExpired as exc:
        exc.output = "\n 'gpg --decrypt' was killed after timeout.\n"
        raise


def setup(query) -> None:
    if not shutil.which("pass"):
        query.add(
            v0.Item(
                id=md_name,
                icon=[icon_path],
                text='"pass" is not installed.',
                subtext='Please install and configure "pass" accordingly.',
                actions=[UrlAction('Open "pass" website', "https://www.passwordstore.org/")],
            )
        )
        return

    # user
    if not user_path.is_file():
        query.add(
            v0.Item(
                id=md_name,
                icon=[icon_path],
                text="Please specify your email address for JIRA",
                subtext="Fill and press [ENTER]",
                actions=[FuncAction("Save user", lambda: save_data(query.string, "user"))],
            )
        )
        return

    # jira server
    if not server_path.is_file():
        query.add(
            v0.Item(
                id=md_name,
                icon=[icon_path],
                text="Please specify the JIRA server to connect to",
                subtext="Fill and press [ENTER]",
                actions=[
                    FuncAction("Save JIRA server", lambda: save_data(query.string, "server"))
                ],
            )
        )
        return

    # api_key
    if not api_key_path.is_file():
        query.add(
            v0.Item(
                id=md_name,
                icon=[icon_path],
                text="Please add api_key",
                subtext="Press to copy the command to run",
                actions=[
                    ClipAction(
                        "Copy command",
                        (
                            "pass insert"
                            f" {api_key_path.relative_to(pass_path).parent / api_key_path.stem}"
                        ),
                    )
                ],
            )
        )
        return


def get_as_subtext_field(field, field_title=None):
    s = ""
    if field:
        s = f"{field} | "
    else:
        return ""

    if field_title:
        s = f"{field_title}:" + s

    return s


def make_transition(jira, issue, a_transition_id):
    print(f'Transitioning issue "{issue.fields.summary[:10]}" -> {a_transition_id}')
    jira.transition_issue(issue, a_transition_id)


def get_as_item(issue: resources.Issue, jira):
    field = get_as_subtext_field

    # first action is default action
    actions = [
        UrlAction("Open in jira", f"{issue.permalink()}"),
        ClipAction("Copy jira URL", f"{issue.permalink()}"),
    ]

    # add an action for each one of the available transitions
    curr_status = issue.fields.status.name
    for a_transition in jira.transitions(issue):
        if a_transition["name"] != curr_status:
            actions.append(
                FuncAction(
                    f'Mark as "{a_transition["name"]}"',
                    lambda a_transition_id=a_transition["id"]: make_transition(
                        jira, issue, a_transition_id
                    ),
                )
            )

    subtext = (
        f"{field(issue.fields.assignee)}"
        f"{field(issue.fields.status.name)}"
        f"{field(issue.fields.issuetype.name)}"
        f"{field(issue.fields.project.key, 'proj')}"
    )
    subtext += prio_to_text[issue.fields.priority.name]

    return v0.Item(
        id=f"{md_name}_{issue.fields.priority.name}",
        icon=[prio_to_icon[issue.fields.priority.name]],
        text=issue.fields.summary,
        subtext=subtext,
        actions=actions,
    )


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
        return "jira "

    def synopsis(self):
        return "ticket title/expr"

    def initialize(self):
        # Called when the extension is loaded (ticked in the settings) - blocking

        # create plugin locations
        for p in (cache_path, config_path, data_path):
            p.mkdir(parents=False, exist_ok=True)

    def finalize(self):
        pass

    def handleQuery(self, query) -> None:
        results = []
        try:
            results_setup = setup(query)
            if results_setup:
                return results_setup

            # TODO Only send request if query ends with dot otherwise add an item to inform the
            # user of this behavior accordingly

            user = load_data("user")
            server = load_data("server")
            api_key = load_api_key()

            # connect to JIRA
            jira = JIRA(server=server, basic_auth=(user, api_key))
            issues = cast(
                ResultList,
                jira.search_issues(
                    (
                        "assignee = currentUser() AND status != 'Done' AND status != 'Won\\'t"
                        " do' AND status != 'Resolved' AND status != 'Rejected'"
                    ),
                    maxResults=max_results_to_request,
                    fields=",".join(fields_to_include),
                    json_result=False,
                ),
            )
            issues.sort(key=lambda issue: issue.fields.priority.id, reverse=False)

            results.append(
                v0.Item(
                    id=md_name,
                    icon=[icon_path],
                    text="Create new issue",
                    actions=[UrlAction("Create new issue", get_create_issue_page(server))],
                )
            )

            if len(query.string.strip()) <= 2:
                for issue in issues[:max_results_to_show]:
                    results.append(get_as_item(issue, jira))
            else:
                desc_to_issue = {issue.fields.summary: issue for issue in issues}
                # do fuzzy search - show relevant issues
                matched = process.extract(
                    query.string.strip(), list(desc_to_issue.keys()), limit=5
                )
                for m in [elem[0] for elem in matched]:
                    results.append(get_as_item(desc_to_issue[m], jira))

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
