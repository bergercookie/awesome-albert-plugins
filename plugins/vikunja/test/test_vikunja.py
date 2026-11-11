"""Tests for the vikunja plugin's query dispatch.

Only the parts that don't need a live Vikunja server: which items a query
yields, and especially that a search with no results falls back to creating a
task instead of opening Vikunja.
"""

from datetime import datetime, timedelta, timezone

from conftest import load_plugin

vikunja = load_plugin("vikunja")


class _Ctx:
    def __init__(self, query):
        self.query = query


class _Task:
    id = "vikunja-task-1"


def _plugin(monkeypatch, results):
    plugin = vikunja.Plugin()
    plugin._base_url = "https://vikunja.example.com"
    plugin._api_token = "token"
    plugin._default_project = "Inbox"
    monkeypatch.setattr(plugin, "_project_map", dict)
    monkeypatch.setattr(
        plugin, "_fetch_search", lambda query, project_map, **kwargs: results
    )
    return plugin


def test_search_without_results_offers_to_add_the_task(monkeypatch):
    plugin = _plugin(monkeypatch, [])

    [item] = next(plugin.items(_Ctx("buy milk")))

    assert item.text == "buy milk"
    assert item.subtext.startswith("No matching tasks")
    assert "Project: Inbox" in item.subtext
    assert item.actions[0].text == "Create task in Vikunja"


def test_search_without_results_still_parses_quick_add_magic(monkeypatch):
    plugin = _plugin(monkeypatch, [])

    [item] = next(plugin.items(_Ctx("buy milk +Home *errand")))

    assert item.text == "buy milk"
    assert "Project: Home" in item.subtext
    assert "Labels: errand" in item.subtext


def test_search_with_results_does_not_offer_to_add_the_task(monkeypatch):
    task = _Task()
    plugin = _plugin(monkeypatch, [task])

    items = next(plugin.items(_Ctx("buy milk")))

    assert items == [task]


# -- searching tasks ---------------------------------------------------------------


def _task(task_id, title, description=""):
    return {"id": task_id, "title": title, "description": description, "done": False}


class _SearchClient:
    def __init__(self, tasks):
        self.tasks = tasks
        self.calls = []

    def get_all_tasks(self, filter_expr=None, search=None, per_page=100, max_pages=20):
        self.calls.append(
            {"filter_expr": filter_expr, "search": search, "per_page": per_page}
        )
        return self.tasks


def _search_plugin(monkeypatch, client):
    plugin = vikunja.Plugin()
    plugin._base_url = "https://vikunja.example.com"
    plugin._api_token = "token"
    monkeypatch.setattr(plugin, "_project_map", dict)
    monkeypatch.setattr(vikunja.Plugin, "client", property(lambda self: client))
    return plugin


def test_get_all_tasks_walks_every_page_and_dedupes(monkeypatch):
    client = vikunja.VikunjaClient("https://vikunja.example.com", "token")
    pages = {
        1: [{"id": 1}, {"id": 2}],
        2: [{"id": 2}, {"id": 3}],
        3: [],
    }
    calls = []

    def fake_get_tasks(filter_expr=None, search=None, per_page=100, page=1):
        calls.append((filter_expr, search, page))
        return pages.get(page, [])

    monkeypatch.setattr(client, "get_tasks", fake_get_tasks)

    tasks = client.get_all_tasks(filter_expr="done = false", search="middle")

    assert [t["id"] for t in tasks] == [1, 2, 3]
    assert calls == [
        ("done = false", "middle", 1),
        ("done = false", "middle", 2),
        ("done = false", "middle", 3),
    ]


def test_search_matches_a_word_from_the_middle_of_a_title(monkeypatch):
    client = _SearchClient([_task(7, "Review the quarterly budget spreadsheet")])
    plugin = _search_plugin(monkeypatch, client)

    items = plugin._fetch_search("budget", {})

    assert [item.text for item in items] == ["Review the quarterly budget spreadsheet"]
    assert client.calls == [
        {"filter_expr": "done = false", "search": "budget", "per_page": 100},
        {"filter_expr": "done = false", "search": None, "per_page": 100},
    ]


def test_fold_ignores_case_and_greek_tonos():
    assert vikunja._fold("ΜΑΡΜΑΡΑ") == "μαρμαρα"  # noqa: RUF001
    assert vikunja._fold("μάρμαρα") == "μαρμαρα"
    assert vikunja._fold("Μάρμαρα") == "μαρμαρα"


def test_search_is_case_and_tonos_insensitive(monkeypatch):
    class _AccentSensitiveClient:
        """Simulates a server whose search does not fold accents: the server
        returns nothing for the unaccented query, so the task can only be found
        by the local pass."""

        def get_all_tasks(self, filter_expr=None, search=None, per_page=100, max_pages=20):
            if search is not None:
                return []
            return [_task(1, "Μάρμαρα στην παραλία")]

    plugin = _search_plugin(monkeypatch, _AccentSensitiveClient())

    items = plugin._fetch_search("ΜΑΡΜΑΡΑ", {})  # noqa: RUF001

    assert [item.text for item in items] == ["Μάρμαρα στην παραλία"]


def test_search_falls_back_to_local_fuzzy_matching_for_typos(monkeypatch):
    class _Client:
        def __init__(self):
            self.searches = []

        def get_all_tasks(self, filter_expr=None, search=None, per_page=100, max_pages=20):
            self.searches.append(search)
            if search is not None:
                return []
            return [_task(1, "Buy milk")]

    client = _Client()
    plugin = _search_plugin(monkeypatch, client)

    items = plugin._fetch_search("mikl", {})

    assert [item.text for item in items] == ["Buy milk"]
    assert client.searches == ["mikl", None]


# -- reminders ----------------------------------------------------------------------


def test_remindme_without_duration_uses_the_default_offset():
    parsed = vikunja.parse_quick_add(
        "Call dentist remindme tomorrow", default_reminder_offset=45 * 60
    )

    assert parsed.title == "Call dentist"
    assert parsed.reminder_offset == 45 * 60
    assert parsed.due is not None


def test_remindme_duration_is_removed_from_the_title():
    parsed = vikunja.parse_quick_add("Call dentist remindme 1h before tomorrow")

    assert parsed.title == "Call dentist"
    assert parsed.reminder_offset == 60 * 60
    assert parsed.due is not None


def test_quoted_text_keeps_remindme_literal():
    parsed = vikunja.parse_quick_add('"Call dentist remindme"')

    assert parsed.title == "Call dentist remindme"
    assert parsed.reminder_offset is None


def test_build_reminder_is_relative_to_the_due_date():
    now = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    due = now + timedelta(hours=2)

    reminder = vikunja._build_reminder(due, 30 * 60, now)

    assert reminder == {
        "reminder": (due - timedelta(minutes=30)).isoformat(),
        "relative_period": -30 * 60,
        "relative_to": "due_date",
    }


def test_add_reminder_preserves_existing_reminders(monkeypatch):
    client = vikunja.VikunjaClient("https://vikunja.example.com", "token")
    now = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    existing = {"reminder": (now + timedelta(hours=1)).isoformat()}
    task = {
        "id": 7,
        "due_date": (now + timedelta(hours=2)).isoformat(),
        "reminders": [existing],
    }
    posted = {}

    monkeypatch.setattr(client, "get_task", lambda task_id: task)

    def fake_request(method, path, params=None, body=None):
        posted.update(body)
        return body

    monkeypatch.setattr(client, "_request", fake_request)

    client.add_reminder(7, 30 * 60, now)

    assert posted["reminders"][0] == existing
    assert posted["reminders"][1]["relative_period"] == -30 * 60
    assert posted["reminders"][1]["relative_to"] == "due_date"


def test_remindme_search_strips_keyword_and_adds_a_reminder_action(monkeypatch):
    task = _task(7, "Pay invoice")
    task["due_date"] = (datetime.now().astimezone() + timedelta(days=1)).isoformat()
    client = _SearchClient([task])
    plugin = _search_plugin(monkeypatch, client)

    [item] = next(plugin.items(_Ctx("invoice remindme 1h")))

    assert client.calls[0]["search"] == "invoice"
    assert item.actions[0].text == "Remind 1h before due"
    assert "Reminder 1h before due" in item.subtext


def test_add_preview_shows_the_configured_default_reminder_offset(monkeypatch):
    plugin = _plugin(monkeypatch, [])
    plugin._default_reminder_offset = "45m"

    [item] = next(plugin.items(_Ctx("buy milk remindme tomorrow")))

    assert "Reminder 45m before due" in item.subtext


def test_invalid_default_reminder_offset_falls_back_to_30m():
    plugin = vikunja.Plugin()
    plugin._default_reminder_offset = "nonsense"

    assert plugin.default_reminder_offset_seconds == 30 * 60


def test_create_action_sends_the_configured_default_reminder(monkeypatch):
    plugin = vikunja.Plugin()
    plugin._base_url = "https://vikunja.example.com"
    plugin._api_token = "token"
    plugin._default_project = "Inbox"
    plugin._default_reminder_offset = "45m"
    created = {}

    class _Client:
        def search_projects(self, name):
            return [{"id": 1, "title": "Inbox"}]

        def create_task(self, project_id, title, **fields):
            created.update(project_id=project_id, title=title, **fields)
            return {"id": 99, **created}

        def search_labels(self, name):
            return []

        def add_label_to_task(self, task_id, label_id):
            pass

    monkeypatch.setattr(vikunja.Plugin, "client", property(lambda self: _Client()))

    plugin._make_add_action("Call dentist remindme tomorrow")()

    assert created["title"] == "Call dentist"
    assert created["due_date"] is not None
    [reminder] = created["reminders"]
    assert reminder["reminder"]
    assert reminder["relative_period"] == -45 * 60
    assert reminder["relative_to"] == "due_date"
