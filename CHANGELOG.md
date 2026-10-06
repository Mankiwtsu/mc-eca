# Changelog

## 0.5.0 – 2026-10-06

Packaging for the course.

* **One-click install pack** (`mc-eca-<version>.mrpack`) for Prism Launcher and the Modrinth
  App: Minecraft 26.3 + Fabric Loader + Fabric API + MC-ECA in a separate instance, with
  *Pause on lost focus* off. Built by `tools/make_mrpack.py` (Fabric API checksums verified).
* **GitHub Actions:** CI builds the mod and runs the Python tests on Linux, macOS and
  Windows (Python 3.10 and 3.14); pushing a `v*` tag publishes a release with the jar,
  the pack and the changelog section.
* **Install guide** rewritten: the pack as the easy way, the official launcher with its own
  game directory (so other Minecraft versions keep working), Windows notes (PATH,
  PowerShell execution policy, firewall).
* **One-page student handout** (`docs/handout.md`), issue template for problem reports.
* Python 3.10 is now the minimum (3.9 is end-of-life); tests that need audio hardware are
  skipped where it's missing.

## 0.4.1 – 2026-10-06

Robustness fixes after the first long test session.

* **Audio on one thread:** all microphone/speaker calls run on a dedicated audio thread,
  so they can't block the connection to Minecraft or the agent (a likely cause of an
  agent that stopped answering after pressing V while it spoke). Spoken sentences are
  queued instead of cutting each other off (two NPCs talk one after another), and
  barge-in also cancels sentences that were still being prepared. Speech models are
  loaded once and shared by all NPCs.
* **Handlers can't kill the agent:** any exception in a handler or timer is printed with
  a traceback and the agent keeps running.
* **Watchdog:** prints where a handler is stuck after 20 s.
* `mceca.clean_reply()` removes leaked JSON/markdown from LLM answers (used in all
  examples).
* Example 10: shorter memory (answers were getting slower: 3.3 s → 5.4 s), no new LLM
  greeting when a player steps out and back in within 30 s. Example 11 has voice
  (different voices for Ava and Bob).
* `MCECA_PORT` environment variable (mod and library) to run a test game next to a
  normal one.

## 0.4.0 – 2026-10-06

Agents that hear each other. Protocol version 4 (older scripts still work).

* **`on_npc_say(speaker, text)`:** NPCs within hearing range hear what another NPC says,
  with `speaker.addressed` when it starts with their name. Works across scripts.
* **Loop guard:** `max_npc_turns` (default 3). The NPC-to-NPC reply count travels with
  every sentence (`say.chain`), so two agents can't keep answering each other, even when
  they are run by different scripts; `mceca.after()` keeps the count too.
* **`look_at(npc)`:** look at another NPC (an `NPC` or the `Speaker`), tracked as it moves.
* `walk_to(player)` now stops 3 blocks away by default (was 2), a more comfortable
  talking distance.
* Example 10: the all-in-one showcase agent (sense → think → act); example 11: two
  agents with a hand-over. StudyLog records `npc_said` with speaker/addressed/chain.

## 0.3.0 – 2026-10-05

Voice. Protocol version 3 (older scripts still work with the new mod).

* **Push-to-talk:** hold **V** near an NPC (rebindable under Controls → MC-ECA). The mod
  now has a small client part (the key) and tells the brain `voice_start` / `voice_end`;
  the action bar shows "Ava is listening…".
* **Python `Voice`:** records the microphone, speech-to-text (`"local"` faster-whisper or
  `"openai"` whisper-1), text-to-speech (`"local"` Piper or `"openai"` tts-1). Spoken
  messages arrive in `on_chat` with `player.spoke == True`; `npc.say()` speaks out loud
  (`speak=False` to only write); barge-in stops the NPC when the player talks.
* What was understood is shown in chat as `<player> [voice] …` (`transcript` command);
  clear messages for "didn't catch that", "nobody close enough", "no voice enabled".
* StudyLog records `voice`, `stt_seconds`, `spoken`, `tts_seconds`.
* `pip install -e "python[voice]"` for the speech packages; the core library stays
  dependency-free.
* Example 09 (voice agent), docs/06-voice.md, voice unit tests (fake microphone and
  fake OpenAI client).

## 0.2.0 – 2026-10-05

Full body and study support. Protocol version 2 (0.1 scripts still work with the new mod).

* **Walking:** `walk_to(player | (x, y, z))`, `follow(player, distance)`, `stop()`, using
  Minecraft's pathfinding (around walls, up steps); `on_arrive`, `on_stuck`.
* **Body language:** `emote()` with six particle emotions; `look_at((x, y, z))`; the head
  keeps looking at the target while the body walks.
* **Items:** `hold`, `give`, `take`.
* **Perception:** `on_player_near` / `on_player_leave` (`notice_range`), `on_click`
  (with the held item), `on_hit`, `surroundings()`, `describe_surroundings()`, `position()`.
* **Timers:** `@mceca.every(seconds)`, `mceca.after(seconds, fn)`.
* **StudyLog:** CSV log per session with participant ids instead of usernames,
  response times and experimenter notes; automatic when passed to `NPC(log=...)`.
* Speech bubbles are always full-bright (readable at night).
* `mceca.check_llm(client, model)`: the LLM examples stop at start-up with a clear
  message when Ollama isn't running, the model isn't downloaded or the OpenAI key is
  missing, instead of answering "Sorry, I lost my train of thought" to every message.
* Examples 06 (proactive greeter), 07 (LLM decides actions via JSON), 08 (pilot-study
  template); docs/05-pilot-studies.md; offline Python unit tests (`python/tests`).

## 0.1.0 – 2026-10-05

First version: text conversations.

* Minecraft mod (Fabric, Minecraft 26.3): NPC body (vanilla mannequin) with skins,
  speech bubble with typewriter effect, thinking bubble, gaze (`look_at`), gestures
  (`nod`, `shake`, `wave`, `crouch`, `jump`), chat routing by distance or name,
  `● connected` status line, `/eca status | list | remove`, `config/mceca.json`.
* Local TCP + JSON-lines protocol (version 1).
* Python library `mceca` (no dependencies): `NPC`, `@on_chat`, actions, automatic
  reconnect, several NPCs per script.
* Examples: hello, OpenAI agent, Ollama agent, Wizard of Oz, LLM-chosen gestures.
* Docs for students, AI assistants (`AGENTS.md`) and maintainers.
