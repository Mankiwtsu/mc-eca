"""
The MC-ECA Python client.

Talks to the MC-ECA Minecraft mod over a local TCP socket. Every message is a
single line of JSON (see docs/03-api-reference.md for the protocol).

Only the Python standard library is used, so `pip install` pulls in nothing else.
"""

from __future__ import annotations

import heapq
import itertools
import json
import os
import queue
import socket
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

PROTOCOL_VERSION = 4
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = int(os.environ.get("MCECA_PORT", "25599"))  # must match the mod (config or MCECA_PORT)

GESTURES = ("nod", "shake", "wave", "crouch", "jump")
EMOTIONS = ("happy", "love", "angry", "sad", "surprised", "confused")

# All events from all NPCs land in this queue; run() takes them out one by one
# and calls your handlers on the main thread.
_events: "queue.Queue[tuple]" = queue.Queue()
_all_npcs: List["NPC"] = []

# Agent-to-agent: while an on_npc_say handler runs, this is how many NPC-to-NPC replies
# led to the sentence being answered (+1). say() sends it along, so the mod can tell the
# next listener, and a chain of NPCs answering NPCs stops after max_npc_turns.
_chain = 0

# Timers for every()/after(): heap of (due_time, sequence, interval_or_None, fn, chain)
_timers: list = []
_timer_lock = threading.Lock()
_timer_seq = itertools.count()

Position = Tuple[float, float, float]


class McEcaError(Exception):
    """Raised when the mod refuses a command (for example an unknown gesture)."""


@dataclass
class Player:
    """A Minecraft player, as seen by the NPC."""

    name: str
    distance: float = 0.0
    spoke: bool = False  # in on_chat: True if the message was spoken (push-to-talk), not typed

    def __str__(self) -> str:
        return self.name


@dataclass
class Speaker:
    """Another NPC that said something this NPC heard (see NPC.on_npc_say)."""

    name: str
    distance: float = 0.0
    addressed: bool = False  # True if the sentence started with this NPC's name ("Bob, ...")

    def __str__(self) -> str:
        return self.name


def _log(msg: str) -> None:
    print(f"[mceca] {msg}", flush=True)


class NPC:
    """
    One NPC character in the Minecraft world.

    Creating an NPC connects to Minecraft (waiting until a world is open), and
    spawns the character next to you. If an NPC with this name already exists in
    the world, it is reused.

        npc = NPC("Ava", skin="alex")

        @npc.on_chat
        def reply(player, text):
            npc.say("You said: " + text)

        npc.run()

    skin:         a default skin ("steve", "alex", "ari", "efe", "kai", "makena",
                  "noor", "sunny", "zuri") or any Minecraft username.
    show_name:    show the name above the NPC's head.
    show_status:  show "● connected" under the name (handy while developing,
                  hide it for user studies).
    notice_range: players coming closer than this many blocks trigger
                  on_player_near (0 = never).
    log:          a StudyLog; everything the NPC hears and does is written to it.
    voice:        a Voice: players can talk to the NPC (hold V) and say() speaks
                  out loud. See mceca.voice.
    max_npc_turns: loop guard for NPCs answering NPCs: after this many replies in a
                  row between NPCs, on_npc_say is no longer called (until a player or
                  a timer starts something new).
    """

    def __init__(
        self,
        name: str,
        skin: Optional[str] = None,
        show_name: bool = True,
        show_status: bool = True,
        notice_range: float = 6.0,
        log=None,
        voice=None,
        max_npc_turns: int = 3,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout: float = 5.0,
    ):
        self.name = name
        self.skin = skin
        self.show_name = show_name
        self.show_status = show_status
        self.notice_range = notice_range
        self.log = log
        self.voice = voice
        self.max_npc_turns = max_npc_turns
        self.host = host
        self.port = port
        self.timeout = timeout

        self._sock: Optional[socket.socket] = None
        self._send_lock = threading.Lock()
        self._ids = itertools.count(1)
        self._pending: Dict[int, "queue.Queue[dict]"] = {}
        self._connected = threading.Event()
        self._handlers: Dict[str, List[Callable]] = {}

        _all_npcs.append(self)
        threading.Thread(target=self._connection_loop, name=f"mceca-{name}", daemon=True).start()
        # Wait in short steps so Ctrl+C keeps working (also on Windows).
        while not self._connected.wait(timeout=0.5):
            pass

    # ------------------------------------------------------------------ events

    def on_chat(self, fn: Callable[[Player, str], None]):
        """
        Decorator: call `fn(player, text)` when a player talks to this NPC.

        A player talks to the NPC by typing in the normal Minecraft chat while
        standing close to it, or by starting the message with its name
        (e.g. "Ava, where is the village?").
        """
        return self._on("chat", fn)

    def on_player_near(self, fn: Callable[[Player], None]):
        """Decorator: `fn(player)` when a player comes within notice_range."""
        return self._on("player_near", fn)

    def on_player_leave(self, fn: Callable[[Player], None]):
        """Decorator: `fn(player)` when a player walks away (or leaves the game)."""
        return self._on("player_left", fn)

    def on_click(self, fn: Callable[[Player, Optional[str]], None]):
        """Decorator: `fn(player, item)` when a player right-clicks the NPC.
        `item` is what the player holds (e.g. "apple"), or None."""
        return self._on("click", fn)

    def on_hit(self, fn: Callable[[Player], None]):
        """Decorator: `fn(player)` when a player punches the NPC (it takes no damage)."""
        return self._on("hit", fn)

    def on_npc_say(self, fn: Callable[[Speaker, str], None]):
        """Decorator: `fn(speaker, text)` when another NPC within hearing range says
        something. speaker.addressed is True if it started with this NPC's name
        ("Bob, can you help?"). Replies made in this handler count towards
        max_npc_turns, so two NPCs can't keep answering each other forever."""
        return self._on("npc_said", fn)

    def on_arrive(self, fn: Callable[[], None]):
        """Decorator: `fn()` when a walk_to() reached its destination."""
        return self._on("arrived", fn)

    def on_stuck(self, fn: Callable[[], None]):
        """Decorator: `fn()` when walk_to()/follow() can't get any closer."""
        return self._on("stuck", fn)

    def _on(self, event: str, fn: Callable) -> Callable:
        self._handlers.setdefault(event, []).append(fn)
        return fn

    # ------------------------------------------------------------- talking

    def say(self, text: str, seconds: Optional[float] = None, speak: bool = True) -> None:
        """Show `text` in a speech bubble above the NPC (and in the chat).
        The bubble stays for `seconds`, or a duration based on the text length.
        If the NPC has a voice, it also says it out loud (speak=False to only write)."""
        text = str(text)
        audio = None
        extra = {}
        if speak and self.voice is not None and self.voice.can_speak and text.strip():
            started = time.monotonic()
            try:
                audio = self.voice.synthesize(text)  # before showing the bubble, so both start together
                extra = {"spoken": True, "tts_seconds": round(time.monotonic() - started, 2)}
            except Exception as e:
                _log(f"text-to-speech failed: {e}")
        self._call("say", _log_extra=extra, text=text, seconds=seconds, chain=_chain or None)
        if audio is not None:
            self.voice.play(*audio)

    def thinking(self, on: bool = True) -> None:
        """Show (or hide) an animated "..." bubble, e.g. while waiting for an LLM.
        It is hidden automatically when the NPC says something."""
        self._call("thinking", on=bool(on))

    # ------------------------------------------------------- body language

    def look_at(self, target: Union["NPC", Speaker, Player, str, Sequence[float], None]) -> None:
        """Keep looking at a player (Player or name), another NPC (NPC object or the
        Speaker from on_npc_say) or a position (x, y, z). `None` stops looking."""
        if target is None:
            self._call("look_at")
        elif isinstance(target, (NPC, Speaker)):
            self._call("look_at", target_npc=target.name)
        elif isinstance(target, (Player, str)):
            self._call("look_at", player=str(target))
        else:
            x, y, z = target
            self._call("look_at", x=x, y=y, z=z)

    def gesture(self, name: str) -> None:
        """Play a gesture: "nod", "shake", "wave", "crouch" or "jump"."""
        self._call("gesture", name=name)

    def emote(self, name: str) -> None:
        """Show an emotion as particles around the head: "happy", "love",
        "angry", "sad", "surprised" or "confused"."""
        self._call("emote", name=name)

    # ------------------------------------------------------------- walking

    def walk_to(
        self,
        target: Union[Player, str, Sequence[float]],
        distance: Optional[float] = None,
        speed: float = 1.0,
    ) -> None:
        """Walk to a player (stops `distance` blocks away, default 3) or to a
        position (x, y, z) (default distance 0.5). Finds a way around walls and up
        steps. Calls on_arrive when there, on_stuck if it can't get there.
        `speed` 1.0 is a calm walk, 2.0 is running."""
        if isinstance(target, (Player, str)):
            self._call("walk_to", player=str(target), distance=distance, speed=speed)
        else:
            x, y, z = target
            self._call("walk_to", x=x, y=y, z=z, distance=distance, speed=speed)

    def follow(self, player: Union[Player, str], distance: float = 3.0, speed: float = 1.0) -> None:
        """Keep following a player, staying about `distance` blocks away,
        until stop() is called."""
        self._call("follow", player=str(player), distance=distance, speed=speed)

    def stop(self) -> None:
        """Stop walking or following."""
        self._call("stop")

    # --------------------------------------------------------------- items

    def hold(self, item: Optional[str]) -> None:
        """Hold an item in the hand, e.g. "apple", "diamond_sword", "map".
        `None` empties the hand."""
        self._call("hold", item=item)

    def give(self, player: Union[Player, str], item: Optional[str] = None, count: int = 1) -> None:
        """Give `count` of `item` to a player. Without `item`, gives what the
        NPC is holding."""
        self._call("give", player=str(player), item=item, count=count)

    def take(self, player: Union[Player, str]) -> Optional[str]:
        """Take one item from the player's hand (the NPC then holds it).
        Returns the item name, e.g. "apple". Raises McEcaError if the hand is empty."""
        return self._call("take", player=str(player)).get("item")

    # ---------------------------------------------------------- perception

    def surroundings(self) -> dict:
        """What the NPC perceives: position, time, weather, biome, what it holds,
        nearby players (distance, held item, health) and mobs. Returns a dict."""
        return self._call("surroundings")

    def describe_surroundings(self) -> str:
        """The surroundings as a few English sentences, ready for an LLM prompt.
        Players are described without their names."""
        return describe(self.surroundings())

    def position(self) -> Optional[Position]:
        """The NPC's position (x, y, z)."""
        pos = self.surroundings().get("position")
        return tuple(pos) if pos else None

    def players(self) -> List[Player]:
        """All players in the world, with their distance to this NPC."""
        result = self._call("players")
        return [Player(p["name"], p.get("distance", 0.0)) for p in result.get("players", [])]

    def remove(self) -> None:
        """Remove this NPC from the world."""
        self._call("remove")

    def run(self) -> None:
        """Handle events forever (until Ctrl+C). Same as `mceca.run()`."""
        run()

    # ---------------------------------------------------------------- plumbing

    def _call(self, cmd: str, _log_extra: Optional[dict] = None, **args) -> dict:
        if not self._connected.is_set():
            _log(f"not connected to Minecraft, skipped {cmd}()")
            return {}
        msg_id = next(self._ids)
        box: "queue.Queue[dict]" = queue.Queue(maxsize=1)
        self._pending[msg_id] = box
        msg = {"id": msg_id, "cmd": cmd, "npc": self.name}
        msg.update({k: v for k, v in args.items() if v is not None})
        try:
            self._send(msg)
            reply = box.get(timeout=self.timeout)
        except (OSError, queue.Empty):
            _log(f"no answer from Minecraft for {cmd}()")
            return {}
        finally:
            self._pending.pop(msg_id, None)
        if not reply.get("ok", False):
            raise McEcaError(f"{cmd}(): {reply.get('error', 'unknown error')}")
        result = reply.get("result") or {}
        if self.log is not None:
            self.log._npc_action(self.name, cmd, dict(args, **(_log_extra or {})), result)
        return result

    def _send(self, msg: dict) -> None:
        data = (json.dumps(msg) + "\n").encode("utf-8")
        with self._send_lock:
            if self._sock is None:
                raise OSError("not connected")
            self._sock.sendall(data)

    def _connection_loop(self) -> None:
        """Connect, keep reading, and reconnect if Minecraft closes the world."""
        waiting_logged = False
        while True:
            try:
                sock = socket.create_connection((self.host, self.port), timeout=2)
            except OSError:
                if not waiting_logged:
                    _log(f"waiting for Minecraft on {self.host}:{self.port} (open a world with the MC-ECA mod) ...")
                    waiting_logged = True
                time.sleep(1)
                continue
            sock.settimeout(None)
            self._sock = sock
            waiting_logged = False
            try:
                self._read_loop(sock)
            except OSError:
                pass
            finally:
                self._connected.clear()
                self._sock = None
                try:
                    sock.close()
                except OSError:
                    pass
            _log("lost connection to Minecraft, reconnecting ...")

    def _read_loop(self, sock: socket.socket) -> None:
        reader = sock.makefile("r", encoding="utf-8")
        # Handshake + spawn happen on this thread, so read replies inline.
        self._handshake(reader)
        for line in reader:
            self._dispatch(json.loads(line))

    def _handshake(self, reader) -> None:
        def request(msg: dict) -> dict:
            self._send(msg)
            while True:
                line = reader.readline()
                if not line:
                    raise OSError("closed during handshake")
                reply = json.loads(line)
                if reply.get("re") == msg["id"]:
                    return reply
                self._dispatch(reply)

        hello = request({"id": 0, "cmd": "hello", "client": "mceca-python", "protocol": PROTOCOL_VERSION})
        if not hello.get("ok"):
            _log(f"Minecraft refused the connection: {hello.get('error')}")
            time.sleep(5)
            raise OSError(hello.get("error", "handshake refused"))

        spawn_msg = {
            "id": 0,
            "cmd": "spawn",
            "npc": self.name,
            "show_name": self.show_name,
            "show_status": self.show_status,
            "notice_range": self.notice_range,
        }
        if self.skin:
            spawn_msg["skin"] = self.skin
        announced = False
        while True:
            reply = request(spawn_msg)
            if reply.get("ok"):
                break
            if not announced:
                _log(f"cannot spawn {self.name} yet: {reply.get('error')} (retrying)")
                announced = True
            time.sleep(1)

        result = reply.get("result") or {}
        verb = "found" if result.get("existing") else "spawned"
        _log(f"connected: {verb} {self.name}")
        self._connected.set()

    def _dispatch(self, msg: dict) -> None:
        if "re" in msg:
            box = self._pending.get(msg["re"])
            if box is not None:
                box.put(msg)
        elif msg.get("event") in ("voice_start", "voice_end"):
            self._voice_event(msg)  # right away, not in the queue: recording must start now
        elif "event" in msg:
            _events.put((self, msg))

    def _voice_event(self, msg: dict) -> None:
        """Push-to-talk. Runs on the connection thread, so no _call() here (that would
        wait for a reply this thread has to read); slow work goes to a worker thread."""
        player = msg.get("player", "?")
        if self.voice is None or not self.voice.can_listen:
            # Answer on release, so this message replaces the "working out what you said" one.
            if msg["event"] == "voice_end" and not msg.get("cancelled"):
                threading.Thread(target=self._safe_call, daemon=True, args=("transcript",), kwargs={
                    "player": player,
                    "error": f"{self.name} can't hear voice: create it with NPC(..., voice=Voice())"}).start()
            return
        if msg["event"] == "voice_start":
            self._voice_distance = msg.get("distance", 0.0)
            self.voice.start_listening()  # returns at once (the audio thread opens the mic)
            return
        threading.Thread(target=self._transcribe, args=(player, bool(msg.get("cancelled"))), daemon=True).start()

    def _transcribe(self, player: str, cancelled: bool) -> None:
        audio = self.voice.stop_listening()  # waits for the audio thread, never on the connection thread
        if cancelled:
            return
        if audio is None:
            self._safe_call("transcript", player=player, text="")
            return
        started = time.monotonic()
        try:
            text = self.voice.transcribe(audio)
        except Exception as e:
            _log(f"speech-to-text failed: {e}")
            self._safe_call("transcript", player=player, error=f"Speech recognition failed: {e}"[:200])
            return
        seconds = round(time.monotonic() - started, 2)
        self._safe_call("transcript", player=player, text=text)
        if text:
            _events.put((self, {"event": "chat", "npc": self.name, "player": player, "text": text,
                                "distance": getattr(self, "_voice_distance", 0.0),
                                "voice": True, "stt_seconds": seconds}))

    def _safe_call(self, cmd: str, **args) -> None:
        try:
            self._call(cmd, **args)
        except McEcaError as e:
            _log(f"error: {e}")

    def _handle_event(self, msg: dict) -> None:
        global _chain
        kind = msg["event"]
        if kind == "npc_said":
            chain = int(msg.get("chain", 0))
            if self.log is not None:
                self.log._event(self.name, kind, None, msg)
            if chain >= self.max_npc_turns:
                _log(f"{self.name} ignores {msg.get('speaker')}: {chain} NPC-to-NPC replies in a row (max_npc_turns)")
                return
            speaker = Speaker(msg.get("speaker", "?"), msg.get("distance", 0.0), bool(msg.get("addressed")))
            _chain = chain + 1
            try:
                for fn in self._handlers.get(kind, []):
                    fn(speaker, msg.get("text", ""))
            finally:
                _chain = 0
            return
        player = Player(msg["player"], msg.get("distance", 0.0), bool(msg.get("voice"))) if "player" in msg else None
        if self.log is not None:
            self.log._event(self.name, kind, player, msg)
        for fn in self._handlers.get(kind, []):
            if kind == "chat":
                fn(player, msg.get("text", ""))
            elif kind == "click":
                fn(player, msg.get("item"))
            elif player is not None:
                fn(player)
            else:
                fn()


# --------------------------------------------------------------------- timers


def every(seconds: float):
    """Decorator: call the function every `seconds` seconds while run() is running,
    on the same thread as the event handlers (so never at the same time as one).

        @mceca.every(20)
        def look_around():
            npc.look_at(None)
    """

    def decorate(fn):
        _schedule(seconds, fn, repeat=True)
        return fn

    return decorate


def after(seconds: float, fn: Callable[[], None]) -> None:
    """Call `fn()` once, `seconds` seconds from now (while run() is running)."""
    _schedule(seconds, fn, repeat=False)


def _schedule(seconds: float, fn: Callable, repeat: bool) -> None:
    # after() inside an on_npc_say handler keeps counting the NPC-to-NPC chain
    chain = 0 if repeat else _chain
    with _timer_lock:
        heapq.heappush(_timers, (time.monotonic() + seconds, next(_timer_seq), seconds if repeat else None, fn, chain))


def _next_timer_in() -> float:
    with _timer_lock:
        return _timers[0][0] - time.monotonic() if _timers else 0.5


def _run_due_timers() -> None:
    global _chain
    while True:
        with _timer_lock:
            if not _timers or _timers[0][0] > time.monotonic():
                return
            due, _, interval, fn, chain = heapq.heappop(_timers)
            if interval is not None:
                heapq.heappush(_timers, (max(due + interval, time.monotonic()), next(_timer_seq), interval, fn, 0))
        _chain = chain
        try:
            _guarded(getattr(fn, "__name__", "timer"), fn)
        finally:
            _chain = 0


# What run() is doing right now, for the watchdog: (description, start time) or None
_busy = None
STUCK_SECONDS = 20.0


def _guarded(what: str, fn, *args) -> None:
    """Call one of your handlers. If it raises, print the error and keep the agent
    running: a bug in one handler shouldn't end a session or a user study."""
    global _busy
    _busy = (what, time.monotonic())
    try:
        fn(*args)
    except McEcaError as e:
        _log(f"error in {what}: {e}")
    except Exception:
        _log(f"error in {what} (the agent keeps running):")
        traceback.print_exc()
    finally:
        _busy = None


def _watchdog(main_thread_id: int) -> None:
    """Print where the agent is stuck if one handler runs suspiciously long."""
    reported = None
    while True:
        time.sleep(2)
        busy = _busy
        if busy is None or busy is reported or time.monotonic() - busy[1] < STUCK_SECONDS:
            continue
        reported = busy
        frame = sys._current_frames().get(main_thread_id)
        stack = "".join(traceback.format_stack(frame)[-6:]) if frame else "(unknown)"
        _log(f"{busy[0]} has been running for {STUCK_SECONDS:.0f} s; new events wait meanwhile. "
             f"It is currently here:\n{stack}")


def run() -> None:
    """Handle events from all NPCs (and timers) forever, until Ctrl+C.

    Handlers run one at a time, in order. While a handler is busy (e.g.
    waiting for an LLM), new messages wait in line.
    """
    threading.Thread(target=_watchdog, args=(threading.get_ident(),), name="mceca-watchdog", daemon=True).start()
    try:
        while True:
            wait = min(0.5, max(0.0, _next_timer_in()))
            try:
                npc, msg = _events.get(timeout=wait)  # timeout keeps Ctrl+C working
            except queue.Empty:
                _run_due_timers()
                continue
            _guarded(f"{npc.name}'s {msg.get('event')} handler", npc._handle_event, msg)
            _run_due_timers()
    except KeyboardInterrupt:
        _log("bye")


# ------------------------------------------------------------------ describing


def clean_reply(text) -> str:
    """Tidy an LLM's answer before an NPC says it: removes code fences and leftover JSON
    (```json, "}, {), wrapping quotes, labels like "Ava:" and *stage directions*.
    Small local models sometimes leak these into the text."""
    import re
    t = str(text or "")
    t = t.split("```")[0]                          # everything after a code fence is junk
    t = re.sub(r'(\{|\}|["\u201d]\s*\]).*$', "", t, flags=re.S)  # { or } or "] start leftover JSON
    t = re.sub(r"\*[^*]{1,60}\*", "", t)         # *smiles*
    t = re.sub(r"^\s*[A-Z][a-z]+:\s+", "", t)       # Ava: Hello -> Hello
    t = " ".join(t.split()).strip()
    if t.endswith('"') and t.count('"') % 2 == 1:  # a closing quote without an opening one
        t = t[:-1].rstrip()
    if t.endswith("\u201d") and t.count("\u201d") > t.count("\u201c"):
        t = t[:-1].rstrip()
    if len(t) >= 2 and t[0] in "\"'\u201c" and t[-1] in "\"'\u201d":
        t = t[1:-1].strip()
    return t.rstrip("{[\u201c ").strip()


def _with_article(item: str) -> str:
    words = item.replace("_", " ")
    return ("an " if words[:1] in "aeiou" else "a ") + words


def describe(s: dict) -> str:
    """Turn a surroundings() dict into a few sentences for an LLM prompt."""
    if not s:
        return ""
    parts = [
        f"It is {s.get('time', '?')} ({'daytime' if s.get('daylight') else 'night'}), "
        f"the weather is {s.get('weather', 'clear')} and you are in a "
        f"{s.get('biome', 'unknown').replace('_', ' ')} area."
    ]
    if s.get("holding"):
        parts.append(f"You are holding {_with_article(s['holding'])}.")
    players = s.get("players", [])
    if players:
        descs = []
        for p in players:
            d = f"one {p['distance']:.0f} blocks away"
            if p.get("holding"):
                d += f" holding {_with_article(p['holding'])}"
            descs.append(d)
        n = len(players)
        parts.append(f"There {'is' if n == 1 else 'are'} {n} player{'s' if n > 1 else ''} near you: " + "; ".join(descs) + ".")
    mobs = s.get("mobs", [])
    if mobs:
        parts.append(
            "Animals and monsters nearby: "
            + ", ".join(f"{_with_article(m['type'])} ({m['distance']:.0f} blocks)" for m in mobs)
            + "."
        )
    return " ".join(parts)
