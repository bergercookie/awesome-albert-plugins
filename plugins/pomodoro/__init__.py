# -*- coding: utf-8 -*-

"""Pomodoro extension. See https://en.wikipedia.org/wiki/Pomodoro_Technique"""

import os
import random
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import gi

import albert as v0

gi.require_version("Notify", "0.7")  # isort:skip
from gi.repository import GdkPixbuf, Notify  # isort:skip


__title__ = "Pomodoro"
__version__ = "0.4.0"
__authors__ = "Manuel Schneider"


class PomodoroTimer:
    def __init__(self):
        self.isBreak = True
        self.timer = None

    def timeout(self, play_sound=True):
        if self.isBreak:
            duration = self.pomodoroDuration * 60
            self.timer = threading.Timer(duration, self.timeout)
            self.endTime = time.time() + duration
            msg = f"Go! [{self.pomodoroDuration} min]"
            if play_sound:
                play_work()
            do_notify(msg=msg, image=icon_path)
            self.timer.start()
        else:
            self.remainingTillLongBreak -= 1
            if self.remainingTillLongBreak == 0:
                self.remainingTillLongBreak = self.count
                duration = self.longBreakDuration * 60
                msg = f"Long Break [{self.breakDuration} min]"
                if play_sound:
                    play_break(long=True)
                do_notify(msg=msg, image=icon_path_break)
            else:
                duration = self.breakDuration * 60
                msg = f"Break [{self.breakDuration} min]"
                if play_sound:
                    play_break()
                do_notify(msg=msg, image=icon_path_break)

            self.endTime = time.time() + duration
            self.timer = threading.Timer(duration, self.timeout)
            self.timer.start()
        self.isBreak = not self.isBreak

    def start(self, pomodoroDuration, breakDuration, longBreakDuration, count):
        self.stop()
        self.pomodoroDuration = pomodoroDuration
        self.breakDuration = breakDuration
        self.longBreakDuration = longBreakDuration
        self.count = count
        self.remainingTillLongBreak = count
        self.isBreak = True
        play_start()
        self.timeout(play_sound=False)

    def stop(self):
        if self.is_active():
            self.timer.cancel()
            self.timer = None
            do_notify(msg="Stopped", image=icon_path_kill)

    def is_active(self):
        return self.timer is not None


icon_path = os.path.dirname(__file__) + "/pomodoro.png"
icon_path_break = os.path.dirname(__file__) + "/pomodoro_break.png"
icon_path_kill = os.path.dirname(__file__) + "/pomodoro_kill.png"

start_sounds_path = Path(__file__).parent.absolute() / "start_sounds"
misc_sounds_path = Path(__file__).parent.absolute() / "misc_sounds"
pomodoro = PomodoroTimer()


def do_notify(msg: str, image=None):
    app_name = "Pomodoro"
    Notify.init(app_name)
    image = image
    n = Notify.Notification.new(app_name, msg, image)
    n.show()


def play_work():
    subprocess.Popen(["cvlc", misc_sounds_path / "get_to_work.mp3"])


def play_break(long: bool = False):
    if long:
        play_sound(num=3)
    else:
        play_sound(num=2)


def play_start():
    sound_path = random.choice([p.absolute() for p in start_sounds_path.iterdir()])
    subprocess.Popen(["cvlc", sound_path])


def play_sound(num):
    for x in range(num):
        t = threading.Timer(
            0.5 * x, lambda: subprocess.Popen(["cvlc", misc_sounds_path / "bing.wav"])
        )
        t.start()


def handleQuery(query):
    tokens = query.string.split()
    if tokens and "pomodoro".startswith(tokens[0].lower()):

        global pomodoro
        pattern = re.compile(query.string, re.IGNORECASE)
        item = v0.Item(
            id=__title__,
            icon=icon_path_kill if pomodoro.is_active() else icon_path,
            text=pattern.sub(lambda m: "<u>%s</u>" % m.group(0), "Pomodoro Timer"),
            completion=query.rawString,
        )

        if len(tokens) == 1 and pomodoro.is_active():
            item.addAction(v0.FuncAction("Stop", lambda p=pomodoro: p.stop()))
            if pomodoro.isBreak:
                whatsNext = "Pomodoro"
            else:
                whatsNext = (
                    "Long break" if pomodoro.remainingTillLongBreak == 1 else "Short break"
                )
            item.subtext = "Stop pomodoro (Next: %s at %s)" % (
                whatsNext,
                time.strftime("%X", time.localtime(pomodoro.endTime)),
            )
            return item

        p_duration = 25
        b_duration = 5
        lb_duration = 15
        count = 4

        item.subtext = "Invalid parameters. Use <i> pomodoro [duration [break duration [long break duration [count]]]]</i>"
        if len(tokens) > 1:
            if not tokens[1].isdigit():
                return item
            p_duration = int(tokens[1])

        if len(tokens) > 2:
            if not tokens[2].isdigit():
                return item
            b_duration = int(tokens[2])

        if len(tokens) > 3:
            if not tokens[3].isdigit():
                return item
            lb_duration = int(tokens[3])

        if len(tokens) > 4:
            if not tokens[4].isdigit():
                return item
            count = int(tokens[4])

        if len(tokens) > 5:
            return item

        item.subtext = (
            "Start new pomodoro timer (%s min/Break %s min/Long break %s min/Count %s)"
            % (p_duration, b_duration, lb_duration, count)
        )
        item.addAction(
            v0.FuncAction(
                "Start",
                lambda p=p_duration, b=b_duration, lb=lb_duration, c=count: pomodoro.start(
                    p, b, lb, c
                ),
            )
        )

        return item
