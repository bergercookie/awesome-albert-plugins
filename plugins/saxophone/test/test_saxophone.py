"""Tests for the saxophone plugin's VLC restart handling.

No VLC or pgrep is started here: the process handling is driven through
monkeypatched module helpers, so these run anywhere.
"""

import signal
import types

from conftest import load_plugin

saxophone = load_plugin("saxophone")


class _Process:
    def __init__(self, pid=42, returncode=None):
        self.pid = pid
        self.returncode = returncode

    def poll(self):
        return self.returncode


class _Ctx:
    def __init__(self, query):
        self.query = query


def _stub_pgrep(monkeypatch, pids=()):
    output = "\n".join(str(pid) for pid in pids)
    monkeypatch.setattr(
        saxophone.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(stdout=output),
    )


def test_vlc_pids_combines_the_tracked_process_and_pgrep_matches(monkeypatch):
    monkeypatch.setattr(saxophone, "vlc_process", _Process(42))
    _stub_pgrep(monkeypatch, [43, 42])

    assert saxophone._vlc_pids() == [42, 43]


def test_vlc_pids_forgets_an_exited_tracked_process(monkeypatch):
    monkeypatch.setattr(saxophone, "vlc_process", _Process(42, returncode=0))
    _stub_pgrep(monkeypatch)

    assert saxophone._vlc_pids() == []
    assert saxophone.vlc_process is None


def test_kill_vlc_sends_sigkill_when_vlc_ignores_sigterm(monkeypatch):
    monkeypatch.setattr(saxophone, "vlc_stop_timeout", 0.0)
    monkeypatch.setattr(saxophone, "_pid_alive", lambda pid: True)
    sent = []
    monkeypatch.setattr(saxophone.os, "kill", lambda pid, sig: sent.append((pid, sig)))

    saxophone._kill_vlc([42])

    assert sent == [(42, signal.SIGTERM), (42, signal.SIGKILL)]


def test_kill_vlc_does_not_kill_a_process_that_quits(monkeypatch):
    monkeypatch.setattr(saxophone, "vlc_stop_timeout", 1.0)
    monkeypatch.setattr(saxophone.time, "sleep", lambda seconds: None)
    alive = iter([True, False, False])
    monkeypatch.setattr(saxophone, "_pid_alive", lambda pid: next(alive))
    sent = []
    monkeypatch.setattr(saxophone.os, "kill", lambda pid, sig: sent.append((pid, sig)))

    saxophone._kill_vlc([42])

    assert sent == [(42, signal.SIGTERM)]


def test_restart_kills_every_vlc_and_relaunches_it(monkeypatch, tmp_path):
    monkeypatch.setattr(saxophone, "vlc_process", _Process(42))
    _stub_pgrep(monkeypatch, [43])
    monkeypatch.setattr(saxophone, "issue_cmd", lambda cmd: None)
    killed = []
    monkeypatch.setattr(saxophone, "_kill_vlc", lambda pids: killed.append(pids))
    launched = []
    monkeypatch.setattr(saxophone, "launch_vlc", lambda: launched.append(True))
    stale_socket = tmp_path / "cvlc.unix"
    stale_socket.write_text("")
    monkeypatch.setattr(saxophone, "vlc_socket", stale_socket)

    saxophone.restart_vlc()

    assert killed == [[42, 43]]
    assert not stale_socket.exists()
    assert launched == [True]
    assert saxophone.vlc_process is None


def test_restart_starts_vlc_when_nothing_is_running(monkeypatch, tmp_path):
    monkeypatch.setattr(saxophone, "vlc_process", None)
    _stub_pgrep(monkeypatch)
    monkeypatch.setattr(saxophone, "issue_cmd", lambda cmd: None)
    monkeypatch.setattr(saxophone, "_kill_vlc", lambda pids: None)
    launched = []
    monkeypatch.setattr(saxophone, "launch_vlc", lambda: launched.append(True))
    monkeypatch.setattr(saxophone, "vlc_socket", tmp_path / "cvlc.unix")

    saxophone.restart_vlc()

    assert launched == [True]


def test_restart_item_is_offered_and_restarts_vlc(monkeypatch):
    plugin = object.__new__(saxophone.Plugin)
    monkeypatch.setattr(saxophone, "streams", [])
    monkeypatch.setattr(saxophone, "is_radio_on", lambda: False)
    restarted = []
    monkeypatch.setattr(saxophone, "restart_vlc", lambda: restarted.append(True))

    items = next(plugin.items(_Ctx("nonsense")))

    restart = [item for item in items if item.text == "Restart VLC"]
    assert len(restart) == 1
    restart[0].actions[0].callable()
    assert restarted == [True]
