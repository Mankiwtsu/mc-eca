# AGENTS.md: guide for AI coding assistants

You are helping a student group in a Human-Agent Interaction course build an
**embodied conversational agent** in Minecraft with MC-ECA. Read this before writing code.

## What the project is

* A **Minecraft mod** (Java, in `mod/`) provides the NPC's *body*: speech bubble, gaze,
  gestures, and it reports what players say. **Students do not modify the mod.** Treat
  it as a fixed API.
* The **brain** is a Python script using the `mceca` library (in `python/mceca/`). This
  is where all student code goes, usually a copy of one of the files in `examples/`.
* The mod and the script talk over a local TCP socket; the library handles that.

## The complete Python API (v0.2)

```python
import mceca
from mceca import NPC, Player, Speaker, StudyLog, Voice, McEcaError, GESTURES, EMOTIONS, check_llm

log = StudyLog(participant="P01", condition="gaze")   # optional CSV log for studies (no usernames)

npc = NPC("Ava",                 # name shown above the head; players address it by name
          skin="alex",           # steve alex ari efe kai makena noor sunny zuri, or a Minecraft username
          show_name=True,        # name tag above the head
          show_status=True,      # "● connected" line under the name (hide for user studies)
          notice_range=6.0,      # distance (blocks) for on_player_near / on_player_leave
          log=log,               # optional: log everything this NPC hears and does
          max_npc_turns=3,       # loop guard for NPCs answering NPCs
          voice=Voice())         # optional: push-to-talk (players hold V) + spoken answers
                                 # Voice(stt="local"|"openai"|None, tts="local"|"openai"|None,
                                 #       language="en", piper_voice=..., openai_voice="nova", ...)
                                 # needs: pip install -e "python[voice]"

# ---- events (decorators); player has .name (str) and .distance (float, blocks)
@npc.on_chat                     # fn(player, text): a player talked to this NPC (typed or spoken;
                                 #   player.spoke is True for push-to-talk messages)
@npc.on_player_near              # fn(player): a player came within notice_range
@npc.on_player_leave             # fn(player): that player walked away / left
@npc.on_click                    # fn(player, item): right-click; item = held item name ("apple") or None
@npc.on_hit                      # fn(player): punched (no damage)
@npc.on_npc_say                  # fn(speaker, text): another NPC nearby spoke; speaker.name,
                                 #   speaker.addressed (True for "Ava, ..."); loop-guarded
@npc.on_arrive                   # fn(): walk_to() reached its goal
@npc.on_stuck                    # fn(): walk_to()/follow() can't get closer

# ---- talking
npc.say("Hello!")                # speech bubble + chat line (+ spoken with a voice); seconds=..., speak=False
npc.thinking(True)               # animated "..." bubble; auto-hidden by say()

# ---- body language
npc.look_at(player)              # or a name, another NPC/Speaker, or a position (x, y, z); None stops
npc.gesture("nod")               # GESTURES: nod, shake, wave, crouch, jump
npc.emote("happy")               # EMOTIONS: happy, love, angry, sad, surprised, confused (particles)

# ---- walking (Minecraft pathfinding; can't open doors or climb ladders)
npc.walk_to(player)              # or (x, y, z); distance=3 for players / 0.5 for positions; speed=1.0 (2.0 = run)
npc.follow(player, distance=3)   # until npc.stop()
npc.stop()

# ---- items (Minecraft item names: "apple", "bread", "diamond_sword", ...)
npc.hold("apple")                # None empties the hand
npc.give(player, "bread", count=1)   # without item: gives what the NPC holds
item = npc.take(player)          # takes 1 item from the player's hand, returns its name; McEcaError if empty

# ---- perception
npc.surroundings()               # dict: position, dimension, biome, time "HH:MM", daylight, weather,
                                 #       holding, walking, players [{name, distance, holding, health}],
                                 #       mobs [{type, distance}]
npc.describe_surroundings()      # the same as English sentences for an LLM prompt (no player names)
npc.position()                   # (x, y, z)
npc.players()                    # -> list[Player] with distance to npc

# ---- timers (run on the handler thread, between events)
@mceca.every(10)                 # call every 10 s
def idle(): ...
mceca.after(5, fn)               # call fn() once in 5 s

# ---- other
log.note("task 1 done")          # your own line in the StudyLog
npc.remove()                     # delete the NPC
npc.run()                        # or mceca.run(): handle events and timers of ALL NPCs until Ctrl+C
```

That is **everything** the NPC can do in this version. Do not invent other methods,
events or gesture/emotion names. If the group needs a behaviour that isn't listed,
build it from these calls (e.g. "walk to the player, then wave, then say …"), or tell
the user it needs a mod change (ask the TA).

### Patterns that work well

* **LLM → behaviour:** ask the model for a JSON object (`response_format={"type": "json_object"}`)
  with fields like `say`, `gesture`, `emotion`, `action`, and validate every field against
  `GESTURES` / `EMOTIONS` / your own action list before calling the NPC
  (see `examples/07_llm_actions.py`).
* **Grounding:** put `npc.describe_surroundings()` in the system prompt every turn.
* **Sense → think → act:** turn every event into an English observation, let one
  `think()` function ask the LLM for a JSON decision, and one `act()` function carry it
  out (see `examples/10_full_agent.py`). New behaviour = a new observation or action.
* **Multi-agent:** answer in `on_npc_say` only when `speaker.addressed`, and look at the
  speaker (see `examples/11_two_agents.py`).
* **Conditions for a study:** a dict of on/off switches chosen with a command-line
  argument, and `StudyLog(participant=..., condition=...)` (see `examples/08_pilot_study.py`).

## Behaviour you can rely on

* `NPC(...)` blocks until Minecraft has a world open, then spawns or re-attaches the NPC.
  It reconnects automatically if the world is closed and reopened.
* Handlers run **one at a time on the main thread**; it's fine for a handler to block on
  an LLM call or `input()`. New messages queue up meanwhile.
* All actions return immediately; animations play in the game. A gesture takes ~1 s.
  `say()` types ~40 characters/s.
* Nothing happens automatically: no gaze, gestures or thinking bubble unless the code
  calls them. Behaviours are experimental conditions the students control.
* `McEcaError` is raised for refused commands (e.g. unknown gesture, player offline,
  empty hand for `take`). Any exception in a handler is printed with a traceback and the
  agent keeps running; a watchdog prints where a handler is stuck after 20 s.
* `walk_to` returns at once; react to arrival in `on_arrive`, not with `sleep`.
* Actions are thread-safe: calling `npc.say` from your own `threading.Thread` is fine.

## LLM usage in this course

* Course OpenAI key, models `gpt-5-nano` (chat), `whisper-1` (speech-to-text),
  `tts-1` (text-to-speech). Load the key with `python-dotenv` from `.env`
  (`OPENAI_API_KEY=...`). **Never hard-code a key, print it, or commit `.env`.**
* For `gpt-5-nano` use `client.chat.completions.create(model="gpt-5-nano", messages=...,
  reasoning_effort="minimal")`. It does not accept `temperature` or `max_tokens`
  (use `max_completion_tokens` if needed).
* Free local alternative: Ollama via the same client:
  `OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")`, model `"gemma3:4b"`.
* Call `mceca.check_llm(client, MODEL)` once after creating the client. It stops with
  a clear message if Ollama isn't running, the model isn't pulled, or the key is missing.
* Keep spoken answers to 1–2 short sentences (speech bubble). Pass LLM text through
  `mceca.clean_reply()` before `npc.say()` (removes leaked JSON/markdown). Tell the model to output
  only the spoken words: no labels, stage directions or emojis.
* Keep conversation history per player in the script; the model has no memory.

## Rules (course + privacy)

* No personal data of participants in logs or files: Minecraft usernames count. Use
  `StudyLog` (it replaces usernames with participant ids) or participant numbers in
  your own logs. Never write `player.name` to a file.
* Collected data must be deleted at the end of the course.
* Keep `.env` out of git (it's in `.gitignore`).

## Running things

```bash
source .venv/bin/activate                              # Windows: .venv\Scripts\activate
pip install -e python -r examples/requirements.txt     # once
python examples/01_hello.py                            # with Minecraft open in a world
```

In-game: `/eca status`, `/eca list`, `/eca remove <name>`.

More detail: `docs/02-your-first-agent.md` (tutorial), `docs/03-api-reference.md`
(full reference and the JSON protocol for other languages).
