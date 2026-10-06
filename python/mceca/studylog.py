"""
StudyLog: a CSV log of everything that happens in a session, for pilot studies.

    from mceca import NPC, StudyLog

    log = StudyLog(condition="gaze", participant="P03")
    npc = NPC("Ava", log=log)      # everything Ava hears and does is logged

Privacy: Minecraft usernames are never written. Each player is replaced by an
alias: the `participant` id you pass in (for the first player seen), or P1, P2, ...
What players *type* is logged as-is, so ask participants not to type personal
information. Delete the logs when the course ends.
"""

from __future__ import annotations

import atexit
import csv
import json
import os
import time
from datetime import datetime
from typing import Dict, Optional

COLUMNS = ["time", "seconds", "participant", "condition", "npc", "actor", "kind", "text", "details"]


class StudyLog:
    """
    One CSV file per session in `folder` (default "logs"), named after the start
    time, participant and condition, e.g. logs/2026-10-05_14-03-22_P03_gaze.csv.

    Columns: time (ISO), seconds (since the start), participant (alias), condition,
    npc, actor ("player", "npc" or "experimenter"), kind (chat, say, gesture, ...),
    text, details (JSON, e.g. {"response_time": 1.84} on an NPC's answer).
    """

    def __init__(self, folder: str = "logs", condition: Optional[str] = None,
                 participant: Optional[str] = None):
        os.makedirs(folder, exist_ok=True)
        self.condition = condition or ""
        self.participant = participant
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        name = "_".join(p for p in (stamp, participant, condition) if p)
        self.path = os.path.join(folder, _safe(name) + ".csv")

        self._start = time.monotonic()
        self._aliases: Dict[str, str] = {}
        self._last_heard: Dict[str, float] = {}  # npc -> time a player last spoke to it
        self._response_times = []
        self._counts: Dict[str, int] = {}

        self._file = open(self.path, "w", newline="", encoding="utf-8-sig")  # -sig: opens cleanly in Excel
        self._csv = csv.writer(self._file)
        self._csv.writerow(COLUMNS)
        self._file.flush()
        atexit.register(self.close)
        print(f"[mceca] logging to {self.path}", flush=True)

    # ------------------------------------------------------------- public

    def note(self, text: str, **details) -> None:
        """Write your own line, e.g. log.note("participant finished task 1")."""
        self._write("", "experimenter", "note", text, details)

    def alias(self, player) -> str:
        """The anonymous id used in the log for a player (or player name)."""
        name = str(player)
        if name not in self._aliases:
            n = len(self._aliases) + 1
            if self.participant:
                self._aliases[name] = self.participant if n == 1 else f"{self.participant}-other{n - 1}"
            else:
                self._aliases[name] = f"P{n}"
        return self._aliases[name]

    def close(self) -> None:
        """Print a short summary and close the file (also happens automatically at exit)."""
        if self._file.closed:
            return
        self._file.close()
        heard = self._counts.get("player:chat", 0)
        said = self._counts.get("npc:say", 0)
        summary = f"[mceca] log saved: {self.path} ({heard} player messages, {said} NPC utterances"
        if self._response_times:
            avg = sum(self._response_times) / len(self._response_times)
            summary += f", mean response time {avg:.2f} s"
        print(summary + ")", flush=True)

    # ------------------------------------------- called by NPC automatically

    def _event(self, npc: str, kind: str, player, msg: dict) -> None:
        details = {}
        if "distance" in msg:
            details["distance"] = msg["distance"]
        if kind == "click":
            details["item"] = msg.get("item")
        if kind == "npc_said":
            details.update(speaker=msg.get("speaker"), addressed=msg.get("addressed"), chain=msg.get("chain"))
        if kind == "chat":
            self._last_heard[npc] = time.monotonic()
            if msg.get("voice"):
                details["voice"] = True
                details["stt_seconds"] = msg.get("stt_seconds")
        actor = "player" if player is not None else "npc"
        who = self.alias(player) if player is not None else ""
        self._write(npc, actor, kind, msg.get("text", ""), details, participant=who)

    def _npc_action(self, npc: str, cmd: str, args: dict, result: dict) -> None:
        if cmd in ("players", "surroundings", "transcript"):
            return  # queries / feedback, not behaviour
        details = {k: v for k, v in args.items() if v is not None and k != "text"}
        who = ""
        if "player" in details:
            who = self.alias(details["player"])
            details["player"] = who
        if cmd in ("give", "take") and result:
            details.update(result)
        text = args.get("text", "")
        if cmd == "say" and npc in self._last_heard:
            rt = round(time.monotonic() - self._last_heard.pop(npc), 3)
            details["response_time"] = rt
            self._response_times.append(rt)
        self._write(npc, "npc", cmd, text, details, participant=who)

    # ------------------------------------------------------------ helpers

    def _write(self, npc, actor, kind, text, details, participant=""):
        if self._file.closed:
            return
        self._counts[f"{actor}:{kind}"] = self._counts.get(f"{actor}:{kind}", 0) + 1
        self._csv.writerow([
            datetime.now().isoformat(timespec="milliseconds"),
            f"{time.monotonic() - self._start:.3f}",
            participant or (self.participant or ""),
            self.condition,
            npc,
            actor,
            kind,
            text,
            json.dumps(details, ensure_ascii=False) if details else "",
        ])
        self._file.flush()  # every line is on disk at once, even if the script crashes


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in name)
