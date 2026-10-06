# 03 – API reference

* [Python library (`mceca`)](#python-library-mceca)
  * [`NPC`](#npc) · [Events](#events) · [Talking](#talking) · [Body language](#body-language)
    · [Walking](#walking) · [Items](#items) · [Perception](#perception)
  * [Timers](#timers) · [`StudyLog`](#studylog) · [Errors & threading](#errors)
* [In-game commands](#in-game-commands)
* [Configuration](#configuration)
* [Protocol (for other languages)](#protocol-for-other-languages)

---

## Python library (`mceca`)

```python
import mceca
from mceca import NPC, Player, Speaker, StudyLog, Voice, McEcaError, GESTURES, EMOTIONS, check_llm
```

The library uses only the Python standard library (Python 3.10+).

<a id="npc"></a>
### `NPC(name, skin=None, show_name=True, show_status=True, notice_range=6.0, log=None, voice=None, max_npc_turns=3, host="127.0.0.1", port=25599, timeout=5.0)`

Connects to Minecraft and spawns the NPC 3 blocks in front of you, or takes control of
it if an NPC with this name already exists. **Blocks until a world is open** and a player
is in it, printing `waiting for Minecraft ...` meanwhile.

| Parameter | Meaning |
|-----------|---------|
| `name` | Shown above the NPC; also how players address it (`Ava, hi`). 1–32 characters, case-insensitive, must be unique. |
| `skin` | A built-in skin: `steve`, `alex`, `ari`, `efe`, `kai`, `makena`, `noor`, `sunny`, `zuri`, or any Minecraft username (e.g. `"Notch"`, needs internet). `None` keeps the current skin. |
| `show_name` | Show the name tag above the head. |
| `show_status` | Show `● connected` / `○ no brain` under the name. Useful while developing; hide it for user studies. |
| `notice_range` | Players coming closer than this (blocks) trigger `on_player_near`; `0` turns it off. |
| `log` | A [`StudyLog`](#studylog): everything this NPC hears and does is written to it. |
| `voice` | A [`Voice`](#voice): players can talk to the NPC (hold V) and `say()` speaks out loud. |
| `max_npc_turns` | Loop guard for agents answering agents: `on_npc_say` is not called anymore after this many NPC-to-NPC replies in a row. |
| `host`, `port` | Where the mod listens. Only change these if you changed the [config](#configuration). |
| `timeout` | Seconds to wait for Minecraft to confirm a command. |

If Minecraft closes the world, the NPC object **reconnects automatically** when you open
it again; your handlers keep working. Commands sent while disconnected are skipped
with a message.

<a id="events"></a>
### Events

Register a handler with a decorator. You can register several per event; they run in order.

| Decorator | Handler | When |
|-----------|---------|------|
| `@npc.on_chat` | `fn(player, text)` | A player talks to the NPC: types in chat within the *hearing range* (default 8 blocks) and this is the nearest NPC, **or** starts the message with the NPC's name (`Ava, …`, `ava: …`, `@Ava …`, any distance in the same world). `text` is the full message. **Spoken messages** (push-to-talk, needs `voice=`) arrive here too, with `player.spoke == True`. |
| `@npc.on_player_near` | `fn(player)` | A player comes within `notice_range`. Also fires for players who are already close when your script (re)connects. |
| `@npc.on_player_leave` | `fn(player)` | That player moves more than `notice_range + 1` blocks away, or leaves the game. |
| `@npc.on_click` | `fn(player, item)` | A player right-clicks the NPC. `item` is what the player holds (`"apple"`) or `None`. |
| `@npc.on_hit` | `fn(player)` | A player punches the NPC. It takes no damage. |
| `@npc.on_npc_say` | `fn(speaker, text)` | Another NPC within hearing range said something. `speaker` is a [`Speaker`](#speaker) (`.name`, `.distance`, `.addressed` = the sentence started with this NPC's name). Replies made in this handler count towards `max_npc_turns`. |
| `@npc.on_arrive` | `fn()` | A `walk_to()` reached its destination. |
| `@npc.on_stuck` | `fn()` | `walk_to()` gave up because the NPC made no progress for ~6 s (wall, water, gap…). With `follow()`, reported once, and it keeps trying. |

`player` is a [`Player`](#player).

<a id="talking"></a>
### Talking

| Method | Effect |
|--------|--------|
| `npc.say(text, seconds=None, speak=True)` | Show `text` in a speech bubble (typewriter effect, ~40 characters/s) and as `<Name> text` in the chat of players within 32 blocks. Stays for `seconds` after typing, or `3 + length/15` s (max 20). Replaces the current bubble and the bubbles of other NPCs within 5 blocks. Turns `thinking` off. Bubble text is cut at 400 characters (the chat gets everything). With a `voice`, also speaks it out loud (`speak=False` to only write). |
| `npc.thinking(on=True)` | Animated `.` `..` `...` bubble until `say()` or `thinking(False)` (max 60 s). |

<a id="body-language"></a>
### Body language

| Method | Effect |
|--------|--------|
| `npc.look_at(target)` | Keep looking at a player (`Player` or name), another NPC (`NPC` object or `Speaker`) or a position `(x, y, z)`. Standing still, the NPC turns its body; while walking, only the head turns (max 70°). `None` stops; the NPC keeps its current direction. |
| `npc.gesture(name)` | About 1 s: `"nod"`, `"shake"` (head), `"wave"` (arm), `"crouch"` (quick double crouch), `"jump"`. A new gesture replaces one still playing. |
| `npc.emote(name)` | Particles around the head for 1 s: `"happy"` (green sparkles), `"love"` (hearts), `"angry"` (storm clouds), `"sad"` (falling drops), `"surprised"` (stars), `"confused"` (smoke). |

`mceca.GESTURES` and `mceca.EMOTIONS` contain the valid names.

<a id="walking"></a>
### Walking

| Method | Effect |
|--------|--------|
| `npc.walk_to(target, distance=None, speed=1.0)` | Walk to a player (stops `distance` blocks away, default 3: a comfortable talking distance) or a position `(x, y, z)` (default 0.5). Finds a way around obstacles and up one-block steps (Minecraft's own pathfinding, up to ~64 blocks), else walks straight. `on_arrive` when there, `on_stuck` when it can't. A player target is tracked while they move. |
| `npc.follow(player, distance=3.0, speed=1.0)` | Keep following the player at about `distance` blocks until `stop()`. Waits while the player is close. |
| `npc.stop()` | Stop walking/following. |

`speed`: `1.0` = calm walk (3.4 blocks/s), `2.0` = run, range 0.2–3.
Limitations: the NPC can't open doors, swims badly and can't climb ladders.

<a id="items"></a>
### Items

Item names are Minecraft's: `"apple"`, `"bread"`, `"diamond_sword"`, `"oak_log"`, `"map"`, …
(see the [Minecraft wiki](https://minecraft.wiki/w/Java_Edition_data_values#Items)).

| Method | Effect |
|--------|--------|
| `npc.hold(item)` | Hold an item in the right hand. `None` empties it. |
| `npc.give(player, item=None, count=1)` | Put `count` items into the player's inventory (dropped at their feet if full). Without `item`: give what the NPC holds (its hand is then empty). |
| `npc.take(player)` | Take one item from the player's hand; the NPC holds it. Returns the item name. `McEcaError` if their hand is empty. Use it in `on_click` for "hand something to the NPC". |

<a id="perception"></a>
### Perception

| Method | Returns |
|--------|---------|
| `npc.surroundings()` | A dict, see below. |
| `npc.describe_surroundings()` | The same as English sentences for an LLM prompt, **without player names**, e.g. *"It is 21:30 (night), the weather is rain and you are in a plains area. There is 1 player near you: one 3 blocks away holding a torch. Animals and monsters nearby: a zombie (9 blocks)."* |
| `npc.position()` | `(x, y, z)` |
| `npc.players()` | All players as `Player`s with their distance to the NPC. |
| `mceca.describe(d)` | `describe_surroundings()` for a dict you already have. |

```python
{
  "position": [12.5, -60.0, 3.5], "dimension": "overworld", "biome": "plains",
  "time": "21:30", "daylight": False, "weather": "rain",     # weather: clear | rain | thunder
  "holding": "bread",              # what the NPC holds, or None
  "walking": False,
  "players": [{"name": "Steve", "distance": 3.1, "holding": "torch", "health": 20.0}],   # within 32 blocks
  "mobs":    [{"type": "zombie", "distance": 9.2}]                                      # within 16 blocks, max 10
}
```

<a id="player"></a>
### `Player`

| Field | |
|-------|---|
| `name` | Minecraft username (`str(player)` gives the same). **Personal data:** don't store it in study logs (`StudyLog` replaces it automatically). |
| `distance` | Distance in blocks (≈ metres) to the NPC when the event happened. |
| `spoke` | In `on_chat`: `True` if the message was spoken (push-to-talk), `False` if typed. |

<a id="speaker"></a>
### `Speaker`

| Field | |
|-------|---|
| `name` | Name of the NPC that spoke. |
| `distance` | Distance between the two NPCs. |
| `addressed` | `True` if the sentence started with the listener's name (`"Bob, …"`, `"@Bob …"`). |

### Other

| | |
|---|---|
| `npc.remove()` | Delete the NPC from the world. |
| `npc.run()` / `mceca.run()` | Handle events and timers of **all** NPCs until Ctrl+C. |
| `mceca.clean_reply(text)` | Tidy an LLM answer before `say()`: removes code fences, leftover JSON (`"}`, `{…}`), `*stage directions*`, `Name:` labels and wrapping quotes. Small local models sometimes leak these into the text. |
| `mceca.check_llm(client, model)` | Start-up check for an OpenAI-compatible client. For Ollama, it checks that Ollama runs and `model` is downloaded; for OpenAI, that a real API key is set. Otherwise it prints what to do and stops the script. |

<a id="voice"></a>
### `Voice(stt="local", tts="local", language="en", whisper_model="base", piper_voice="en_US-lessac-medium", openai_voice="alloy", openai_client=None, interruptible=True, volume=1.0, input_device=None, output_device=None)`

Speech for an NPC: `NPC("Ava", voice=Voice())`. `stt`/`tts` are `"local"` (offline:
faster-whisper / Piper), `"openai"` (`whisper-1` / `tts-1`) or `None`. Needs
`pip install -e "python[voice]"`. All options and tips: [06 – Voice](06-voice.md).

<a id="timers"></a>
### Timers

```python
@mceca.every(10)          # every 10 seconds while run() is running
def idle():
    npc.look_at(None)

mceca.after(3, lambda: npc.say("Still there?"))   # once, in 3 seconds
```

Timers run on the same thread as event handlers, never at the same time as one.

<a id="studylog"></a>
### `StudyLog(folder="logs", condition=None, participant=None)`

A CSV log of a session for pilot studies. Pass it to `NPC(..., log=log)` and every event
and action of that NPC is written automatically; add your own lines with `log.note(...)`.

```python
log = StudyLog(condition="expressive", participant="P03")   # logs/2026-10-05_14-03-22_P03_expressive.csv
npc = NPC("Ava", log=log)
log.note("task 1 started")
```

| Column | |
|--------|---|
| `time` | ISO timestamp (ms) |
| `seconds` | seconds since the log started |
| `participant` | `participant` for the first player seen, `P03-other1`, … for others (or `P1`, `P2`, … without `participant`). **Usernames are never written.** |
| `condition` | as given |
| `npc` | NPC name |
| `actor` | `player`, `npc` or `experimenter` (notes) |
| `kind` | event (`chat`, `player_near`, `click`, …) or action (`say`, `gesture`, `walk_to`, …) |
| `text` | what was said |
| `details` | JSON: distance, gesture name, item, … and `response_time` (seconds from a player's message to the NPC's `say`) |

Each line is written to disk immediately. At exit (also Ctrl+C), the log closes and
prints a summary (messages, utterances, mean response time). `log.alias(player)` gives
the anonymous id of a player. See [05 – Pilot studies](05-pilot-studies.md).

<a id="errors"></a>
### Errors & threading

`McEcaError` is raised when Minecraft refuses a command (unknown gesture, player not
online, empty hand for `take`, …). **Any** exception in one of your handlers or timers
is printed with its traceback, and the agent keeps running. A bug in one reply shouldn't
end a session or a user study.

**Watchdog:** if a handler runs longer than 20 s, `run()` prints which handler and the
line it is stuck on (e.g. a hanging LLM call). Events that arrive meanwhile are handled
afterwards.

`run()` calls handlers and timers **one at a time on the main thread**. While one waits
(for an LLM, or `input()`), new events queue up and are handled afterwards, in order.
Actions are thread-safe if you start your own threads.

---

## In-game commands

Type these in the Minecraft chat (no cheats needed):

| Command | |
|---------|---|
| `/eca status` | Is the bridge running, on which port, how many scripts are connected. |
| `/eca list` | All NPCs and whether a script (brain) is connected to each. |
| `/eca remove <name>` | Delete an NPC (e.g. `/eca remove Ava`). |

---

## Configuration

`config/mceca.json` inside your Minecraft folder (e.g.
`%APPDATA%\.minecraft\config\mceca.json`) is created on first start. Edit it while the
game is closed:

```json
{
  "port": 25599,
  "bind_address": "127.0.0.1",
  "hearing_range": 8.0,
  "chat_range": 32.0
}
```

| Key | Default | Meaning |
|-----|---------|---------|
| `port` | `25599` | Port the scripts connect to. Change it if something else uses it (then pass `port=` to `NPC`). |
| `bind_address` | `127.0.0.1` | `127.0.0.1` = only scripts on this computer may connect. `0.0.0.0` = also other computers in the network (Wizard of Oz on a second laptop). |
| `hearing_range` | `8.0` | Blocks within which the nearest NPC hears chat. |
| `chat_range` | `32.0` | Blocks within which players see the NPC's words in their chat. |

The environment variable `MCECA_PORT` overrides the port in both the mod and the Python
library (e.g. a second Minecraft for testing next to your normal one).

---

## Protocol (for other languages)

You don't need this for Python. It's here if you want to write the brain in another
language (JavaScript, C#, …) or debug by hand.

* **Transport:** TCP, `127.0.0.1:25599`, UTF-8.
* **Framing:** one JSON object per line (newline-delimited JSON).
* **Requests** (you → mod) have an `id` (any integer) and a `cmd`.
* **Replies** (mod → you) carry the same id in `re`: `{"re": 1, "ok": true, "result": {...}}`
  or `{"re": 1, "ok": false, "error": "..."}`.
* **Events** (mod → you, any time) have an `event` field and the `npc` name.
* **Version:** the current protocol is **4**. Send the highest version you need in
  `hello`; the mod refuses versions newer than its own.

### Session

```jsonc
→ {"id": 1, "cmd": "hello", "protocol": 4}
← {"re": 1, "ok": true, "result": {"server": "mc-eca", "protocol": 4}}

→ {"id": 2, "cmd": "spawn", "npc": "Ava", "skin": "alex", "show_name": true, "show_status": true, "notice_range": 6}
← {"re": 2, "ok": true, "result": {"existing": false}}
   // error "no player in the world yet" → retry after a second

← {"event": "chat", "npc": "Ava", "player": "Steve", "text": "Hello!", "distance": 3.1}

→ {"id": 3, "cmd": "say", "npc": "Ava", "text": "Hi Steve!"}
← {"re": 3, "ok": true, "result": {}}
```

`spawn` also **subscribes** the connection to the NPC's events. You only receive events
for NPCs you spawned (or re-attached to) on this connection.

### Commands

| `cmd` | Fields (besides `npc`) | Result |
|-------|------------------------|--------|
| `hello` | `protocol` | `server`, `protocol` |
| `spawn` | optional `skin`, `show_name`, `show_status`, `notice_range` | `existing` |
| `say` | `text`, optional `seconds`, `chain` (NPC-to-NPC reply count, see `npc_said`) | – |
| `thinking` | `on` | – |
| `look_at` | `player`, **or** `target_npc`, **or** `x`,`y`,`z`, **or** nothing (stop) | – |
| `gesture` | `name`: `nod` `shake` `wave` `crouch` `jump` | – |
| `emote` | `name`: `happy` `love` `angry` `sad` `surprised` `confused` | – |
| `walk_to` | `player` **or** `x`,`y`,`z`; optional `distance`, `speed` | – |
| `follow` | `player`, optional `distance`, `speed` | – |
| `stop` | – | – |
| `hold` | `item` (omit to empty the hand) | – |
| `give` | `player`, optional `item`, `count` | `item`, `count` |
| `take` | `player` | `item`, `count` |
| `surroundings` | – | see [Perception](#perception) |
| `transcript` | `player`, `text` **or** `error` | – (shows `<player> [voice] text` in chat; empty text → "didn't catch that"; `error` → shown to the player) |
| `players` | (`npc` optional) | `players`: list of `{name, distance}` |
| `remove` | – | – |

### Events

| `event` | Fields (besides `npc`) |
|---------|------------------------|
| `chat` | `player`, `text`, `distance` |
| `player_near` | `player`, `distance` |
| `player_left` | `player`, optional `distance` |
| `click` | `player`, `distance`, `item` (or null) |
| `hit` | `player`, `distance` |
| `arrived` | – |
| `stuck` | – |
| `npc_said` | `speaker`, `text`, `distance`, `addressed`, `chain`: another NPC within hearing range spoke. `chain` = how many NPC-to-NPC replies led to it; when you answer, send `chain + 1` in your `say`, and stop answering at your limit. |
| `voice_start` | `player`, `distance`: the player pressed the talk key near this NPC: start recording |
| `voice_end` | `player`, `seconds`, optional `cancelled`: key released: stop recording, transcribe, answer with `transcript` |

### Try it by hand

With a world open, connect with `nc` (macOS/Linux) and type JSON lines:

```bash
nc 127.0.0.1 25599
```

```
{"id":1,"cmd":"hello","protocol":4}
{"id":2,"cmd":"spawn","npc":"Test"}
{"id":3,"cmd":"say","npc":"Test","text":"I was typed by hand!"}
{"id":4,"cmd":"emote","npc":"Test","name":"love"}
```
