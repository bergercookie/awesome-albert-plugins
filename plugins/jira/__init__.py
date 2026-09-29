""" Jira Issue Tracking."""

import shutil
import subprocess
import traceback
from pathlib import Path
from typing import Iterator, List, Optional, cast

from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    PluginInstance,
    StandardItem,
    openUrl,
    setClipboardText,
)
from fuzzywuzzy import process

from jira import JIRA, resources
from jira.client import ResultList

# initial configuration -----------------------------------------------------------------------

md_name = "Jira"
md_description = "Jira Issue Tracking"
md_iid = "5.0"
md_version = "0.3"
md_maintainers = ["Nikos Koukis"]
md_lib_dependencies = ["fuzzywuzzy", "jira"]
md_url = "https://github.com/bergercookie/jira-albert-plugin"
__simplename__ = "jira"
md_bin_dependencies = ["gpg", "pass"]
ICON_PATH = Path(__file__).parent / "jira_blue.png"
ICON_PATH_BR = Path(__file__).parent / "jira_bold_red.png"
ICON_PATH_R = Path(__file__).parent / "jira_red.png"
ICON_PATH_Y = Path(__file__).parent / "jira_yellow.png"
ICON_PATH_G = Path(__file__).parent / "jira_green.png"
ICON_PATH_LG = Path(__file__).parent / "jira_light_green.png"

pass_path = Path().home() / ".password-store"
api_key_path = pass_path / "jira-albert-plugin" / "api-key.gpg"

max_results_to_request = 50
max_results_to_show = 5
fields_to_include = ["assignee", "issuetype", "priority", "project", "status", "summary"]

prio_to_icon = {
    "Highest": ICON_PATH_BR,
    "High": ICON_PATH_R,
    "Medium": ICON_PATH_Y,
    "Low": ICON_PATH_G,
    "Lowest": ICON_PATH_LG,
}

prio_to_text = {"Highest": "↑", "High": "↗", "Medium": "-", "Low": "↘", "Lowest": "↓"}

# supplementary functions ---------------------------------------------------------------------


def get_create_issue_page(server: str) -> str:
    return server + "/secure/CreateIssue!default.jspa"


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


def make_transition(jira, issue, a_transition_id):
    print(f'Transitioning issue "{issue.fields.summary[:10]}" -> {a_transition_id}')
    jira.transition_issue(issue, a_transition_id)


def get_as_subtext_field(field, field_title=None):
    s = ""
    if field:
        s = f"{field} | "
    else:
        return ""

    if field_title:
        s = f"{field_title}:" + s

    return s


# main plugin class ------------------------------------------------------------
class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        # create plugin locations
        self.cache_path = Path(self.cacheLocation()) / __simplename__
        self.config_path = Path(self.configLocation()) / __simplename__
        self.data_path = Path(self.dataLocation()) / __simplename__
        for p in (self.cache_path, self.config_path, self.data_path):
            p.mkdir(parents=True, exist_ok=True)

        self.user_path = self.config_path / "user"
        self.server_path = self.config_path / "server"

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def defaultTrigger(self):
        return "jira "

    def synopsis(self, query):
        return "ticket title/expr"

    def save_data(self, data: str, data_name: str):
        """Save a piece of data in the configuration directory."""
        with open(self.config_path / data_name, "w") as f:
            f.write(data)

    def load_data(self, data_name) -> str:
        """Load a piece of data from the configuration directory."""
        with open(self.config_path / data_name, "r") as f:
            data = f.readline().strip().split()[0]

        return data

    def setup(self, query_str: str) -> Optional[List[StandardItem]]:
        """Return the setup item the user has to act on, if any."""
        if not shutil.which("pass"):
            return [
                StandardItem(
                    id=f"{self.id()}-pass-missing",
                    icon_factory=self.makeIcon,
                    text='"pass" is not installed.',
                    subtext='Please install and configure "pass" accordingly.',
                    actions=[
                        Action(
                            "open",
                            'Open "pass" website',
                            lambda: openUrl("https://www.passwordstore.org/"),
                        )
                    ],
                )
            ]

        # user
        if not self.user_path.is_file():
            return [
                StandardItem(
                    id=f"{self.id()}-user",
                    icon_factory=self.makeIcon,
                    text="Please specify your email address for JIRA",
                    subtext="Fill and press [ENTER]",
                    actions=[
                        Action(
                            "save",
                            "Save user",
                            lambda query_str=query_str: self.save_data(query_str, "user"),
                        )
                    ],
                )
            ]

        # jira server
        if not self.server_path.is_file():
            return [
                StandardItem(
                    id=f"{self.id()}-server",
                    icon_factory=self.makeIcon,
                    text="Please specify the JIRA server to connect to",
                    subtext="Fill and press [ENTER]",
                    actions=[
                        Action(
                            "save",
                            "Save JIRA server",
                            lambda query_str=query_str: self.save_data(query_str, "server"),
                        )
                    ],
                )
            ]

        # api_key
        if not api_key_path.is_file():
            return [
                StandardItem(
                    id=f"{self.id()}-api-key",
                    icon_factory=self.makeIcon,
                    text="Please add api_key",
                    subtext="Press to copy the command to run",
                    actions=[
                        Action(
                            "copy",
                            "Copy command",
                            lambda: setClipboardText(
                                (
                                    "pass insert"
                                    f" {api_key_path.relative_to(pass_path).parent / api_key_path.stem}"
                                )
                            ),
                        )
                    ],
                )
            ]

        return None

    def get_as_item(self, issue: resources.Issue, jira) -> StandardItem:
        field = get_as_subtext_field

        # first action is default action
        actions = [
            Action("open", "Open in jira", lambda url=issue.permalink(): openUrl(url)),
            Action(
                "copy",
                "Copy jira URL",
                lambda url=issue.permalink(): setClipboardText(url),
            ),
        ]

        # add an action for each one of the available transitions
        curr_status = issue.fields.status.name
        for a_transition in jira.transitions(issue):
            if a_transition["name"] != curr_status:
                actions.append(
                    Action(
                        "transition",
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

        # an issue's key is stable across queries, unlike its (mutable) summary
        issue_key = getattr(issue, "key", None) or issue.permalink()
        return StandardItem(
            id=f"{self.id()}-{issue_key}",
            icon_factory=self._makeIcon(prio_to_icon[issue.fields.priority.name]),
            text=issue.fields.summary,
            subtext=subtext,
            actions=actions,
        )

    @staticmethod
    def _makeIcon(path):
        """Return a zero-arg icon factory for the given image path."""
        return lambda: Icon.image(path)

    def items(self, ctx) -> Iterator[List[StandardItem]]:
        results = []
        try:
            results_setup = self.setup(ctx.query)
            if results_setup:
                yield results_setup
                return

            # TODO Only send request if query ends with dot otherwise add an item to inform the
            # user of this behavior accordingly

            user = self.load_data("user")
            server = self.load_data("server")
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
                StandardItem(
                    id=f"{self.id()}-create-issue",
                    icon_factory=self.makeIcon,
                    text="Create new issue",
                    actions=[
                        Action(
                            "open",
                            "Create new issue",
                            lambda url=get_create_issue_page(server): openUrl(url),
                        )
                    ],
                )
            )

            if len(ctx.query.strip()) <= 2:
                for issue in issues[:max_results_to_show]:
                    results.append(self.get_as_item(issue, jira))
            else:
                desc_to_issue = {issue.fields.summary: issue for issue in issues}
                # do fuzzy search - show relevant issues
                matched = process.extract(ctx.query.strip(), list(desc_to_issue.keys()), limit=5)
                for m in [elem[0] for elem in matched]:
                    results.append(self.get_as_item(desc_to_issue[m], jira))

        except Exception:  # user to report error
            trace = traceback.format_exc()
            critical(trace)
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
