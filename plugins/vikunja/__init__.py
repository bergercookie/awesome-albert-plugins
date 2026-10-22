# -*- coding: utf-8 -*-
"""Vikunja task manager plugin for Albert launcher.

Search, filter, complete, open and quickly add Vikunja (https://vikunja.io) tasks
straight from Albert, using Vikunja's REST API (/api/v1).
"""

import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    Notification,
    PluginInstance,
    StandardItem,
    openUrl
)

md_iid = "5.0"
md_version = "1.0"
md_name = "Vikunja"
md_description = "Search, filter, complete and quickly add Vikunja tasks"
md_license = "MIT"
md_url = "https://github.com/albertlauncher/albert-plugin-python"
md_authors = ["@bergercookie"]

ICON_PATH = Path(__file__).parent / "icon.svg"

DEFAULT_TRIGGER = "v "

CONFIG_BASE_URL = "base_url"
CONFIG_API_TOKEN = "api_token"
CONFIG_DEFAULT_PROJECT = "default_project"
CONFIG_VERIFY_SSL = "verify_ssl"

CACHE_TTL_SECONDS = 2.0

PRIORITY_NAMES = {
    1: "Low priority",
    2: "Medium priority",
    3: "High priority",
    4: "Urgent",
    5: "DO NOW",
}

FILTER_LABELS = {
    "today": "Today's tasks",
    "overdue": "Overdue tasks",
    "all": "All open tasks",
}

FILTER_EXPRESSIONS = {
    "today": "done = false && due_date >= now/d && due_date < now/d+1d",
    "overdue": "done = false && due_date < now/d",
    "all": "done = false",
}

TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Vikunja API client
# ---------------------------------------------------------------------------

def error(*args, **kwargs):
    print("Vikunja plugin error:", *args, **kwargs, file=sys.stderr)

class VikunjaError(Exception):
    """Raised for any problem talking to the Vikunja API."""


class VikunjaClient:
    """Minimal client for the parts of the Vikunja REST API this plugin needs."""

    def __init__(self, base_url: str, token: str, verify_ssl: bool = True, timeout: float = 8.0):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.token = (token or "").strip()
        self.verify_ssl = verify_ssl
        self.timeout = timeout

    @property
    def api_root(self) -> str:
        return f"{self.base_url}/api/v1"

    def _ssl_context(self):
        if self.verify_ssl:
            return None
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _request(self, method: str, path: str, params: Optional[dict] = None,
                 body: Optional[dict] = None) -> Any:
        if not self.base_url:
            raise VikunjaError("Vikunja base URL is not configured. Open the plugin settings to set it up.")
        if not self.token:
            raise VikunjaError("Vikunja API token is not configured. Open the plugin settings to set it up.")

        url = f"{self.api_root}{path}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            query = urllib.parse.urlencode(clean, doseq=True)
            if query:
                url = f"{url}?{query}"

        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", f"Bearer {self.token}")
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=self._ssl_context()) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                payload = e.read().decode("utf-8", "replace")
                try:
                    detail = json.loads(payload).get("message", payload)
                except (json.JSONDecodeError, AttributeError):
                    detail = payload
            except Exception:
                pass
            if e.code == 401:
                raise VikunjaError("Vikunja rejected the API token (401). Check it in the plugin settings.") from e
            raise VikunjaError(f"Vikunja API error {e.code}: {detail or e.reason}") from e
        except urllib.error.URLError as e:
            raise VikunjaError(f"Could not reach Vikunja at {self.base_url}: {e.reason}") from e
        except TimeoutError as e:
            raise VikunjaError("The request to Vikunja timed out.") from e

    # -- tasks ---------------------------------------------------------

    def get_tasks(self, filter_expr: Optional[str] = None, search: Optional[str] = None,
                   per_page: int = 100) -> list:
        params = {
            "per_page": per_page,
            "sort_by": ["due_date", "priority"],
            "order_by": ["asc", "desc"],
        }
        if filter_expr:
            params["filter"] = filter_expr
        if search:
            params["s"] = search
        return self._request("GET", "/tasks", params=params) or []

    def get_task(self, task_id: int) -> dict:
        return self._request("GET", f"/tasks/{task_id}")

    def update_task(self, task_id: int, **changes) -> dict:
        # Vikunja's update endpoint replaces the whole task record, so we
        # fetch the current one first and only overwrite the given fields -
        # sending a partial body (e.g. just {"done": true}) would blank out
        # the title and every other field.
        task = self.get_task(task_id)
        task.update(changes)
        return self._request("POST", f"/tasks/{task_id}", body=task)

    def delete_task(self, task_id: int) -> Any:
        return self._request("DELETE", f"/tasks/{task_id}")

    def create_task(self, project_id: int, title: str, **fields) -> dict:
        body = {"title": title}
        body.update({k: v for k, v in fields.items() if v is not None})
        return self._request("PUT", f"/projects/{project_id}/tasks", body=body)

    # -- projects --------------------------------------------------------

    def get_projects(self, per_page: int = 100) -> list:
        return self._request("GET", "/projects", params={"per_page": per_page}) or []

    def search_projects(self, name: str, per_page: int = 50) -> list:
        return self._request("GET", "/projects", params={"s": name, "per_page": per_page}) or []

    # -- labels ------------------------------------------------------------

    def search_labels(self, name: str, per_page: int = 50) -> list:
        return self._request("GET", "/labels", params={"s": name, "per_page": per_page}) or []

    def create_label(self, title: str) -> dict:
        return self._request("PUT", "/labels", body={"title": title})

    def add_label_to_task(self, task_id: int, label_id: int) -> Any:
        return self._request("PUT", f"/tasks/{task_id}/labels", body={"label_id": label_id})


# ---------------------------------------------------------------------------
# Quick Add Magic - a Python re-implementation of Vikunja's title parsing
# (+project, *label, !priority, natural-language due dates). Vikunja only
# parses this client-side (its frontend), the REST API itself expects
# already-structured fields, so the plugin has to do this parsing itself.
# ---------------------------------------------------------------------------

@dataclass
class ParsedTask:
    title: str
    project: Optional[str] = None
    labels: list = field(default_factory=list)
    priority: Optional[int] = None
    due: Optional[datetime] = None


LABEL_RE = re.compile(r"\*(?:\"([^\"]+)\"|'([^']+)'|(\S+))")
PROJECT_RE = re.compile(r"\+(?:\"([^\"]+)\"|'([^']+)'|(\S+))")
PRIORITY_RE = re.compile(r"(?<!\S)!([1-5])(?!\S)")

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
WEEKDAY_ALT = "|".join(WEEKDAYS.keys())

TIME_RE = re.compile(
    r"\b(?:at|@)\s+([0-9]{1,2})(?::([0-9]{2}))?\s*(am|pm)?\b", re.IGNORECASE
)
IN_RE = re.compile(
    r"\bin\s+(\d+)\s*(minutes?|mins?|hours?|hrs?|days?|weeks?|wks?|months?|mos?|years?|yrs?)\b",
    re.IGNORECASE,
)
TONIGHT_RE = re.compile(r"\btonight\b", re.IGNORECASE)
TOMORROW_RE = re.compile(r"\btomorrow\b", re.IGNORECASE)
TODAY_RE = re.compile(r"\btoday\b", re.IGNORECASE)
NEXT_WEEKDAY_RE = re.compile(rf"\bnext\s+({WEEKDAY_ALT})\b", re.IGNORECASE)
WEEKDAY_RE = re.compile(rf"\b({WEEKDAY_ALT})\b", re.IGNORECASE)
THIS_WEEKEND_RE = re.compile(r"\bthis\s+weekend\b", re.IGNORECASE)
NEXT_WEEK_RE = re.compile(r"\bnext\s+week\b", re.IGNORECASE)
NEXT_MONTH_RE = re.compile(r"\bnext\s+month\b", re.IGNORECASE)
END_OF_MONTH_RE = re.compile(r"\bend\s+of\s+month\b", re.IGNORECASE)
ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
SLASH_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
DOT_DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b")


def _default_time(now: datetime) -> tuple:
    """Rounds up to the next full hour, used as the due time when only a date
    (no explicit "at HH:MM") was given."""
    if now.minute or now.second or now.microsecond:
        rounded = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        rounded = now
    return rounded.hour, rounded.minute


def _combine(d: date, hm: tuple, tzinfo) -> datetime:
    return datetime(d.year, d.month, d.day, hm[0], hm[1], tzinfo=tzinfo)


def _upcoming_weekday(now: datetime, target: int, include_today: bool) -> date:
    days_ahead = (target - now.weekday()) % 7
    if days_ahead == 0 and not include_today:
        days_ahead = 7
    return (now + timedelta(days=days_ahead)).date()


def _extract_time(text: str) -> tuple:
    """Looks for an explicit "at 5pm" / "at 17:30" style time. Returns
    (remaining_text, (hour, minute) or None)."""
    m = TIME_RE.search(text)
    if not m:
        return text, None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    meridiem = (m.group(3) or "").lower()
    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return text, None
    remaining = text[:m.start()] + text[m.end():]
    return remaining, (hour, minute)


def _extract_due_date(text: str, now: datetime) -> tuple:
    """Extracts a due date/time expression from `text`. Returns
    (remaining_text, datetime or None)."""

    def consume(match, day_or_dt):
        remaining = text[:match.start()] + text[match.end():]
        remaining, explicit_time = _extract_time(remaining)
        if isinstance(day_or_dt, datetime):
            dt = day_or_dt
            if explicit_time:
                dt = dt.replace(hour=explicit_time[0], minute=explicit_time[1], second=0, microsecond=0)
        else:
            hm = explicit_time or _default_time(now)
            dt = _combine(day_or_dt, hm, now.tzinfo)
        return remaining.strip(), dt

    m = IN_RE.search(text)
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith(("min",)):
            return consume(m, now + timedelta(minutes=amount))
        if unit.startswith(("hour", "hr")):
            return consume(m, now + timedelta(hours=amount))
        if unit.startswith(("day",)):
            return consume(m, (now + timedelta(days=amount)).date())
        if unit.startswith(("week", "wk")):
            return consume(m, (now + timedelta(weeks=amount)).date())
        if unit.startswith(("month", "mo")):
            return consume(m, (now + timedelta(days=amount * 30)).date())
        if unit.startswith(("year", "yr")):
            return consume(m, (now + timedelta(days=amount * 365)).date())

    m = TONIGHT_RE.search(text)
    if m:
        remaining = text[:m.start()] + text[m.end():]
        remaining, explicit_time = _extract_time(remaining)
        hm = explicit_time or (21, 0)
        return remaining.strip(), _combine(now.date(), hm, now.tzinfo)

    m = TOMORROW_RE.search(text)
    if m:
        return consume(m, (now + timedelta(days=1)).date())

    m = TODAY_RE.search(text)
    if m:
        return consume(m, now.date())

    m = NEXT_WEEKDAY_RE.search(text)
    if m:
        target = WEEKDAYS[m.group(1).lower()]
        return consume(m, _upcoming_weekday(now, target, include_today=False))

    m = THIS_WEEKEND_RE.search(text)
    if m:
        if now.weekday() in (5, 6):
            return consume(m, now.date())
        return consume(m, _upcoming_weekday(now, 5, include_today=False))

    m = NEXT_WEEK_RE.search(text)
    if m:
        return consume(m, (now + timedelta(days=7)).date())

    m = NEXT_MONTH_RE.search(text)
    if m:
        year, month = (now.year, now.month + 1) if now.month < 12 else (now.year + 1, 1)
        return consume(m, date(year, month, 1))

    m = END_OF_MONTH_RE.search(text)
    if m:
        year, month = (now.year, now.month + 1) if now.month < 12 else (now.year + 1, 1)
        return consume(m, date(year, month, 1) - timedelta(days=1))

    # Bare weekday name, e.g. "friday" -> the next upcoming occurrence.
    m = WEEKDAY_RE.search(text)
    if m:
        target = WEEKDAYS[m.group(1).lower()]
        return consume(m, _upcoming_weekday(now, target, include_today=False))

    m = ISO_DATE_RE.search(text)
    if m:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return consume(m, d)
        except ValueError:
            pass

    m = SLASH_DATE_RE.search(text)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), m.group(3)
        year = int(y) if y else now.year
        if year < 100:
            year += 2000
        for month, day in ((a, b), (b, a)):  # try month/day first, then day/month
            try:
                return consume(m, date(year, month, day))
            except ValueError:
                continue

    m = DOT_DATE_RE.search(text)
    if m:
        day, month, y = int(m.group(1)), int(m.group(2)), m.group(3)
        year = int(y) if y else now.year
        if year < 100:
            year += 2000
        try:
            return consume(m, date(year, month, day))
        except ValueError:
            pass

    # No date keyword found - but a bare "at 5pm" still counts as "today".
    remaining, explicit_time = _extract_time(text)
    if explicit_time:
        return remaining.strip(), _combine(now.date(), explicit_time, now.tzinfo)

    return text, None


def parse_quick_add(text: str, now: Optional[datetime] = None) -> ParsedTask:
    """Parses Vikunja "Quick Add Magic" syntax out of free-form task text:
    +project, *label (quote multi-word ones), !1..!5 priority, and natural
    language due dates ("tomorrow", "in 3 days", "next monday", "23/12", ...).
    Wrapping the whole text in quotes disables all parsing.
    """
    now = now or datetime.now().astimezone()
    text = text.strip()

    if len(text) >= 2 and ((text[0] == text[-1] == '"') or (text[0] == text[-1] == "'")):
        return ParsedTask(title=text[1:-1].strip())

    labels = []
    for m in LABEL_RE.finditer(text):
        labels.append(next(g for g in m.groups() if g))
    text = LABEL_RE.sub(" ", text)

    project = None
    m = PROJECT_RE.search(text)
    if m:
        project = next(g for g in m.groups() if g)
        text = PROJECT_RE.sub(" ", text, count=1)

    priority = None
    m = PRIORITY_RE.search(text)
    if m:
        priority = int(m.group(1))
        text = PRIORITY_RE.sub(" ", text, count=1)

    text, due = _extract_due_date(text, now)

    title = WHITESPACE_RE.sub(" ", text).strip(" -,.")

    return ParsedTask(title=title, project=project, labels=labels, priority=priority, due=due)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _strip_html(html: str) -> str:
    return WHITESPACE_RE.sub(" ", TAG_RE.sub(" ", html or "")).strip()


def _parse_api_datetime(value: Optional[str]):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.year <= 1:  # Vikunja's "unset" sentinel (Go zero time)
        return None
    return dt.astimezone()


def _fuzzy_score(query: str, haystacks: list) -> float:
    """Scores `query` against each (text, weight) haystack: an exact substring
    hit scores highest, otherwise the best per-word similarity ratio is used
    (below a similarity floor this counts as no match, to avoid short queries
    spuriously matching unrelated long text)."""
    q = query.lower().strip()
    if not q:
        return 0.0
    best = 0.0
    for text, weight in haystacks:
        text = (text or "").lower()
        if not text:
            continue
        if q in text:
            score = 0.9 + 0.1 * (len(q) / max(len(text), 1))
        else:
            words = text.split()
            score = max((SequenceMatcher(None, q, w).ratio() for w in words), default=0.0)
            if score < 0.6:
                score = 0.0
        best = max(best, score * weight)
    return best


# ---------------------------------------------------------------------------
# The plugin
# ---------------------------------------------------------------------------

class Plugin(PluginInstance, GeneratorQueryHandler):

    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

        self._base_url = self.readConfig(CONFIG_BASE_URL, str) or ""
        self._api_token = self.readConfig(CONFIG_API_TOKEN, str) or ""
        self._default_project = self.readConfig(CONFIG_DEFAULT_PROJECT, str) or ""
        verify = self.readConfig(CONFIG_VERIFY_SSL, bool)
        self._verify_ssl = True if verify is None else verify

        self._cache = {}  # key -> (timestamp, value)

    def defaultTrigger(self):
        return DEFAULT_TRIGGER

    def synopsis(self, query):
        return "today | overdue | all | add <task text> | <search text>"

    # -- config, bound to the settings widget below -----------------------

    @property
    def base_url(self):
        return self._base_url

    @base_url.setter
    def base_url(self, value):
        self._base_url = (value or "").strip()
        self.writeConfig(CONFIG_BASE_URL, self._base_url)

    @property
    def api_token(self):
        return self._api_token

    @api_token.setter
    def api_token(self, value):
        self._api_token = (value or "").strip()
        self.writeConfig(CONFIG_API_TOKEN, self._api_token)

    @property
    def default_project(self):
        return self._default_project

    @default_project.setter
    def default_project(self, value):
        self._default_project = (value or "").strip()
        self.writeConfig(CONFIG_DEFAULT_PROJECT, self._default_project)

    @property
    def verify_ssl(self):
        return self._verify_ssl

    @verify_ssl.setter
    def verify_ssl(self, value):
        self._verify_ssl = bool(value)
        self.writeConfig(CONFIG_VERIFY_SSL, self._verify_ssl)

    def configWidget(self):
        return [
            {
                "type": "label",
                "text": "Create a personal API token in Vikunja under Settings → API Tokens "
                        "(it needs read/write access to tasks, projects and labels), then fill it "
                        "in below together with your Vikunja instance's base URL.",
            },
            {
                "type": "lineedit",
                "property": "base_url",
                "label": "Vikunja base URL",
                "widget_properties": {"placeholderText": "https://vikunja.example.com"},
            },
            {
                "type": "lineedit",
                "property": "api_token",
                "label": "API token",
                "widget_properties": {"echoMode": 2, "placeholderText": "tk_..."},  # QLineEdit::Password
            },
            {
                "type": "lineedit",
                "property": "default_project",
                "label": "Default project for new tasks",
                "widget_properties": {"placeholderText": "e.g. Inbox (used when no +project is given)"},
            },
            {
                "type": "checkbox",
                "property": "verify_ssl",
                "label": "Verify TLS certificate (turn off only for self-signed setups)",
            },
        ]

    # -- plumbing -----------------------------------------------------------

    @property
    def client(self) -> VikunjaClient:
        return VikunjaClient(self._base_url, self._api_token, self._verify_ssl)

    @staticmethod
    def makeIcon():
        return Icon.image(ICON_PATH)

    def _cached(self, key, fn):
        now = time.time()
        cached = self._cache.get(key)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]
        value = fn()
        self._cache[key] = (now, value)
        return value

    def _project_map(self) -> dict:
        def fetch():
            try:
                projects = self.client.get_projects()
            except VikunjaError:
                projects = []
            return {p["id"]: p.get("title", "") for p in projects}
        return self._cached("projects", fetch)

    def _task_web_url(self, task_id) -> str:
        return f"{self._base_url}/tasks/{task_id}"

    def _filter_web_url(self, key: str) -> str:
        base = self._base_url
        today = datetime.now().astimezone().date()
        start = today.isoformat()
        tomorrow = (today + timedelta(days=1)).isoformat()
        if key == "today":
            return f"{base}/tasks/by/upcoming?from={start}&to={tomorrow}&showOverdue=false"
        if key == "overdue":
            return f"{base}/tasks/by/upcoming?from={start}&to={start}&showOverdue=true"
        return f"{base}/"

    # -- item builders --------------------------------------------------

    def _config_hint_item(self):
        return StandardItem(
            id="vikunja-config-hint",
            text="Vikunja is not configured yet",
            subtext="Open Albert's settings → Plugins → Vikunja to set the base URL and API token",
            icon_factory=self.makeIcon,
        )

    def _error_item(self, message: str):
        return StandardItem(
            id="vikunja-error",
            text="Vikunja error",
            subtext=message,
            icon_factory=self.makeIcon,
        )

    def _empty_item(self, message: str):
        return StandardItem(
            id="vikunja-empty",
            text=message,
            subtext="Press Enter to open Vikunja in your browser",
            icon_factory=self.makeIcon,
            actions=[Action("open", "Open Vikunja", lambda: openUrl(f"{self._base_url}/"))],
        )

    def _nav_items(self, active: Optional[str] = None) -> list:
        items = []
        for key, label in FILTER_LABELS.items():
            text = f"● {label}" if key == active else label
            items.append(StandardItem(
                id=f"vikunja-nav-{key}",
                text=text,
                subtext=f"Type \"{key}\" (or press Tab) to list these tasks here · Enter opens Vikunja",
                icon_factory=self.makeIcon,
                input_action_text=key,
                actions=[Action("open", "Open in Vikunja", lambda k=key: openUrl(self._filter_web_url(k)))],
            ))
        return items

    def _add_hint_item(self):
        return StandardItem(
            id="vikunja-add-hint",
            text="Add a task",
            subtext='Keep typing, e.g. "Call dentist +Personal *errand !3 tomorrow at 5pm"',
            icon_factory=self.makeIcon,
        )

    def _add_preview_item(self, raw_text: str, no_matches: bool = False):
        now = datetime.now().astimezone()
        parsed = parse_quick_add(raw_text, now)
        if not parsed.title:
            return self._add_hint_item()

        bits = [f"Project: {parsed.project or self._default_project or 'not set - configure a default'}"]
        if parsed.labels:
            bits.append("Labels: " + ", ".join(parsed.labels))
        if parsed.priority:
            bits.append(PRIORITY_NAMES.get(parsed.priority, f"Priority {parsed.priority}"))
        if parsed.due:
            bits.append("Due " + parsed.due.strftime("%a %d %b %H:%M"))
        subtext = "Create task in Vikunja · " + "  ·  ".join(bits)
        if no_matches:
            subtext = "No matching tasks · " + subtext

        return StandardItem(
            id="vikunja-add-preview",
            text=parsed.title,
            subtext=subtext,
            icon_factory=self.makeIcon,
            actions=[Action("create", "Create task in Vikunja", self._make_add_action(raw_text))],
        )

    def _task_item(self, task: dict, project_map: dict):
        done = bool(task.get("done"))
        title = task.get("title") or "(untitled task)"
        due_dt = _parse_api_datetime(task.get("due_date"))
        now = datetime.now().astimezone()

        parts = []
        if done:
            parts.append("Done")
        elif due_dt:
            when = due_dt.strftime("%a %d %b %H:%M")
            parts.append(f"Overdue · due {when}" if due_dt < now else f"Due {when}")
        else:
            parts.append("No due date")

        priority = task.get("priority") or 0
        if priority and not done:
            parts.append(PRIORITY_NAMES.get(priority, f"Priority {priority}"))

        labels = task.get("labels") or []
        if labels:
            parts.append(", ".join(l.get("title", "") for l in labels))

        project_name = project_map.get(task.get("project_id"))
        if project_name:
            parts.append(project_name)

        description = _strip_html(task.get("description") or "")
        if description:
            parts.append(description[:80] + ("…" if len(description) > 80 else ""))

        task_id = task["id"]
        complete_text = "Mark as not done" if done else "Mark as done"

        return StandardItem(
            id=f"vikunja-task-{task_id}",
            text=title,
            subtext="  ·  ".join(parts),
            icon_factory=self.makeIcon,
            input_action_text=title,
            actions=[
                Action("toggle-done", complete_text,
                       lambda tid=task_id, d=done: self._toggle_done(tid, not d)),
                Action("open", "Open in Vikunja",
                       lambda tid=task_id: openUrl(self._task_web_url(tid))),
                Action("delete", "Delete task",
                       lambda tid=task_id, t=title: self._delete_task(tid, t)),
            ],
        )

    # -- actions --------------------------------------------------------

    def _toggle_done(self, task_id, done):
        try:
            self.client.update_task(task_id, done=done)
            self._cache.clear()
            Notification(title="Vikunja", text="Marked as done" if done else "Marked as not done").send()
        except VikunjaError as e:
            print(str(e))
            Notification(title="Vikunja — error", text=str(e)).send()

    def _delete_task(self, task_id, title):
        try:
            self.client.delete_task(task_id)
            self._cache.clear()
            Notification(title="Vikunja", text=f'Deleted "{title}" (recoverable from trash for 30 days)').send()
        except VikunjaError as e:
            error(str(e))
            Notification(title="Vikunja — error", text=str(e)).send()

    def _resolve_project(self, name: Optional[str]) -> tuple:
        client = self.client
        wanted = (name or self._default_project or "").strip()
        if not wanted:
            raise VikunjaError("No project given and no default project configured.")
        candidates = client.search_projects(wanted)
        for p in candidates:
            if p.get("title", "").lower() == wanted.lower():
                return p["id"], p["title"]
        if candidates:
            return candidates[0]["id"], candidates[0]["title"]
        raise VikunjaError(f'No Vikunja project found matching "{wanted}".')

    def _resolve_labels(self, names: list) -> list:
        client = self.client
        ids = []
        for name in names:
            existing = client.search_labels(name)
            match = next((l for l in existing if l.get("title", "").lower() == name.lower()), None)
            if match is None:
                match = client.create_label(name)
            ids.append(match["id"])
        return ids

    def _make_add_action(self, raw_text: str):
        def _do_add():
            now = datetime.now().astimezone()
            parsed = parse_quick_add(raw_text, now)
            try:
                project_id, project_name = self._resolve_project(parsed.project)
                task = self.client.create_task(
                    project_id,
                    parsed.title,
                    due_date=parsed.due.isoformat() if parsed.due else None,
                    priority=parsed.priority or 0,
                )
                for label_id in self._resolve_labels(parsed.labels):
                    self.client.add_label_to_task(task["id"], label_id)
                self._cache.clear()
                Notification(title="Vikunja", text=f'Created "{parsed.title}" in {project_name}').send()
            except VikunjaError as e:
                error(str(e))
                Notification(title="Vikunja — error", text=str(e)).send()
        return _do_add

    # -- query dispatch ---------------------------------------------------

    def _fetch_filtered(self, key: str, project_map: dict) -> list:
        tasks = self._cached(
            f"filter:{key}",
            lambda: self.client.get_tasks(filter_expr=FILTER_EXPRESSIONS[key]),
        )
        return [self._task_item(t, project_map) for t in tasks]

    def _fetch_search(self, query: str, project_map: dict) -> list:
        tasks = self._cached("search:all-open", lambda: self.client.get_tasks(filter_expr="done = false", per_page=200))
        scored = []
        for t in tasks:
            score = _fuzzy_score(query, [
                (t.get("title"), 1.0),
                (_strip_html(t.get("description") or ""), 0.6),
            ])
            if score >= 0.3:
                scored.append((score, t))
        scored.sort(key=lambda st: st[0], reverse=True)
        return [self._task_item(t, project_map) for _, t in scored[:30]]

    def items(self, ctx):
        query = ctx.query.strip()
        lower = query.lower()

        if not self._base_url or not self._api_token:
            yield [self._config_hint_item()]
            return

        try:
            if lower == "":
                yield self._nav_items() + [self._add_hint_item()]
                return

            if lower in FILTER_EXPRESSIONS:
                project_map = self._project_map()
                results = self._fetch_filtered(lower, project_map)
                yield results or [self._empty_item(f"No {FILTER_LABELS[lower].lower()}")]
                return

            if lower in ("add", "new") or lower.startswith("add ") or lower.startswith("new "):
                raw = query.split(" ", 1)[1] if " " in query else ""
                yield [self._add_preview_item(raw.strip())]
                return

            project_map = self._project_map()
            results = self._fetch_search(query, project_map)
            yield results or [self._add_preview_item(query, no_matches=True)]

        except VikunjaError as e:
            error(str(e))
            yield [self._error_item(str(e))]
