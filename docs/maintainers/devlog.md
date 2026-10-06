# Development log

A step-by-step record of how MC-ECA was designed and built, with the reasons behind
each decision. Newest entries at the bottom.

---

## 2026-10-05: Planning

### Goal

A reusable framework for the Human-Agent Interaction course (2nd-year bachelor,
"Embodied Conversational Agents"), so student groups can build and pilot-test an
embodied conversational agent inside **Minecraft Java Edition**. It is an alternative to
the existing options (NAO/Mini robots via the Robots-in-de-Klas API, Unity + Convai,
the Godot template, the Python HAI-Template).

Course constraints that shaped the design (from the course materials):

* groups of 4, ~90 hours each, a **pilot** design-and-evaluation study;
* verbal dialogue **plus one additional modality**;
* each group gets an **OpenAI key** (`gpt-5-nano`, `whisper-1`, `tts-1`);
* students may use AI to write code; they work on their own laptops;
* no personal data of participants, and data is deleted after the course.

### Decision: no Convai

Convai worked well in Unity, but its free plan allows only 100 interactions per month
(1 user, no long-term memory), and there is no Java/Minecraft SDK. The course already
provides an OpenAI key, and Ollama offers a free local alternative. So the LLM is
whatever the student's script calls, and nothing in the mod depends on a specific
provider.

### Decision: Minecraft body + Python brain

* **Body (mod, Java):** spawns the NPC, renders speech, gaze and gestures, and reports
  chat. Written once by the maintainer; students never touch Java.
* **Brain (Python script):** receives events, calls an LLM (or a human Wizard-of-Oz),
  and sends actions. It mirrors how students already program the NAO robot
  (`rie.dialogue.say`, `rom.optional.behavior.play`) and fits the Python skills and the
  course's OpenAI examples.
* **Nothing automatic:** the NPC only does what the script says, so each modality is an
  experimental variable the group controls.

### Decision: versions

* **Minecraft 26.3** (latest stable on 2026-10-05; 26.4 is due in Q4 2026). Fixed for the
  whole course year so nothing breaks mid-semester.
* **Fabric** (loader 0.19.5, Fabric API 0.161.0+26.3, Loom 1.18): lightweight and quick
  to update. Minecraft 26.x ships **unobfuscated**, so the code uses Mojang's real
  names, which also makes it easier for others to read.

### Decision: vanilla entities only (server-side mod)

* The NPC body is the vanilla **mannequin** entity (since 1.21.9): player-shaped, any
  skin, no AI of its own.
* The speech bubble is a vanilla **text display** entity.
* So the mod needs no client-side code. It works in singleplayer, and players can join a
  server running MC-ECA without installing anything.

### Decision: protocol

Plain **TCP + newline-delimited JSON** on `127.0.0.1:25599` instead of WebSockets or
gRPC:

* no dependencies on either side (the Python library is standard-library only);
* easy to debug by hand with `nc`;
* any language can be a brain.

Requests carry an `id`, replies echo it in `re`, events carry `event`. A `hello`
handshake checks the protocol version.

---

## 2026-10-05: Toolchain

1. Looked up versions: Mojang's version manifest gave the latest release **26.3**, which
   needs Java **25** (`javaVersion.majorVersion`). Fabric meta gave loader **0.19.5**. The
   official `fabric-example-mod` gave Loom `1.18-SNAPSHOT`, Fabric API `0.161.0+26.3` and
   Gradle 9.7.1.
2. Installed the tools:
   ```bash
   brew install openjdk@25 ollama
   ```
3. Copied the Gradle wrapper and build files from `fabric-example-mod` into `mod/`.
   Removed the client source set and mixins (not needed), and raised the wrapper's
   download timeout (`networkTimeout=120000`, `retries=3`) because the first Gradle
   download timed out on a slow connection.
4. First build: `./gradlew build` (first run ~17 minutes to download Minecraft and its
   libraries on that connection).
   * Gotcha: running `build genSources` together fails with an implicit-dependency
     error. Run `genSources` on its own.

## 2026-10-05: Finding the Minecraft APIs

Since 26.x is unobfuscated, the classes can be read straight from
`~/.gradle/caches/fabric-loom/26.3/minecraft-merged.jar` with `javap`:

* Entity types moved to `net.minecraft.world.entity.EntityTypes` (e.g. `EntityTypes.MANNEQUIN`).
* `Mannequin.setProfile`, `setDescription` and `setHideDescription` are **private**, and
  so are most `Display` / `TextDisplay` setters. They're opened with a Fabric **class
  tweaker** (`mceca.classtweaker`, header `classTweaker v1 official`, registered as
  `accessWidener` in `fabric.mod.json` and `loom.accessWidenerPath` in `build.gradle`).
* Skins: `ResolvableProfile.CODEC` parsed from JSON, `{"texture": "entity/player/slim/alex", "model": "slim"}`
  for built-in skins or `{"name": "Notch"}` for a player's skin.
* Fabric API events used: `ServerLifecycleEvents` (start/stop the bridge),
  `ServerTickEvents.END_SERVER_TICK` (animate), `ServerMessageEvents.CHAT_MESSAGE`
  (player chat), `ServerEntityEvents.ENTITY_LOAD` (re-link NPCs after reload, delete
  stale bubbles), `CommandRegistrationCallback` (`/eca`).

## 2026-10-05: Implementation (v0.1.0)

* `Bridge` / `BridgeClient`: TCP server bound to 127.0.0.1, one reader and one writer
  thread per connected script. World-changing commands are handed to the server thread
  with `server.execute`.
* `NpcManager`:
  * Spawns NPCs 3 blocks in front of the first player, facing them. If another NPC
    already stands there, it steps 2 blocks sideways.
  * Finds existing NPCs by entity tag `mceca_npc` + name, so a restarted script takes
    over the same NPC.
  * Routes chat to the NPC whose name the message starts with, else to the nearest NPC
    within 8 blocks.
  * Shows "has no brain connected" in the action bar if nobody controls that NPC.
* `NpcController`, every tick:
  * **gaze:** smooth turn towards the target player, max 20°/tick;
  * **gestures:** offsets on head pitch (nod) or yaw (shake), arm swings (wave), pose
    changes (crouch), a velocity impulse (jump);
  * **speech bubble:** typewriter effect at 2 characters per tick, reading time
    `3 + length/15` s, white background, 0.8 scale, placed just above the name tag.
  * The line under the name shows `● connected` / `○ no brain`.
* Speech bubbles are tagged `mceca_bubble`. They're removed when the server stops, and
  any left over are deleted when they load, so they never pile up in saves.
* Python library `mceca`:
  * `NPC` connects in a background thread, does the handshake and spawn, and
    reconnects when the world closes;
  * `run()` dispatches events to handlers one at a time on the main thread;
  * actions wait for the mod's reply (5 s timeout) and raise `McEcaError` on refusal.
* Examples:
  1. hello (no AI);
  2. OpenAI `gpt-5-nano` with `reasoning_effort="minimal"`;
  3. Ollama `gemma3:4b` through the OpenAI-compatible endpoint;
  4. Wizard of Oz;
  5. the LLM picks a gesture tag per answer.

## 2026-10-05: Testing

* **Automated client game test** (`fabric-client-gametest-api`): creates a world, waits
  for a brain, chats, takes screenshots. Checked:
  * spawning and the Alex skin;
  * the `connected` status line;
  * typewriter bubble and chat line;
  * nod, shake, wave, crouch, jump and the thinking bubble;
  * Ollama conversations;
  * Wizard of Oz with scripted stdin;
  * two NPCs (side-by-side spawning, routing by name, `show_status=False`);
  * `/eca status` and `/eca list`;
  * reconnecting after the world closes.
* **Problems found and fixed through the screenshots:**
  * Bubble too high above the name: placed relative to the hitbox height, so it also
    follows crouching.
  * Long LLM answers ran off the top of the screen: smaller text (0.8), wider lines,
    spawn distance from 2.5 to 3 blocks.
  * `gemma3:4b` took "your words appear in a speech bubble" literally and wrote
    `[Speech Bubble] Hello…`. The persona now says "reply only with the words Ava
    says out loud: no labels…".
  * Two NPCs' bubbles overlapped: a new speaker now clears the bubbles of NPCs within
    5 blocks (turn-taking; the chat keeps the full record), and the spawn spacing went
    from 1.5 to 2 blocks.
  * An NPC in an unloaded chunk could be duplicated when a script spawned it again: the
    older copy is now discarded when it loads.
* **Gradle gotcha:** after `LICENSE` was added, `jar` failed with *"Invocation of
  'project' references a Gradle script object … configuration cache"*. The closure that
  renames the license read `project.archives_base_name` while the task ran. Fix: read it
  into a local variable while configuring (see `build.gradle`).
* **macOS gotcha:** with the display asleep, the test client hung in
  `SDL_GL_SwapWindow`. Fix: `caffeinate -dimsu` and a screen that's awake.
* **Production check:** the built jar on a real Fabric dedicated server (`server.jar` from
  Fabric meta, `online-mode=false`). It loaded, the bridge listened, and the protocol
  answered correctly: handshake, version mismatch, "no player yet", unknown NPC, invalid
  JSON.
* **Not yet tested:** `02_openai_agent.py` with a real course key (no key on the dev
  machine); Windows and Linux (only macOS was available).

## 2026-10-05: Step 2 (v0.2.0): body, perception, study support

### What was added and why

| Feature | Why (HAI) |
|---------|-----------|
| `walk_to`, `follow`, `stop`, `on_arrive`, `on_stuck` | movement and **proxemics** as a modality: approaching vs. waiting, follow distance |
| `look_at((x, y, z))`, head turns while walking | gaze towards objects ("over there"), and eye contact while moving |
| `emote()`: six particle emotions | emotion display as a modality (Minecraft faces can't change) |
| `hold`, `give`, `take`, `on_click(item)` | object-based interaction: handing things over, shopkeeper/helper tasks |
| `on_player_near` / `on_player_leave`, `on_hit` | proactive behaviour (greeting), reactions to the player's body, not only their words |
| `surroundings()` / `describe_surroundings()` | grounding the LLM in the situation (time, weather, animals, what the player holds) |
| `@mceca.every`, `mceca.after` | idle behaviour and timed prompts without threads |
| `StudyLog` | pilot studies need logs; the course forbids personal data, so usernames are replaced by participant ids at write time |

### Design decisions

* **Walking without AI.** Mannequins have no AI or navigation. Options considered:
  1. straight-line steering only, which is simple but gets stuck at every wall;
  2. riding an invisible mob, which is hacky, adds hitbox and interaction side effects
     and shows visual glitches;
  3. **borrowing the pathfinder**, which was chosen.

  A zombie is created with `EntityTypes.ZOMBIE.create(...)` but **never added to the
  world**. It is placed at the NPC, `setOnGround(true)` makes
  `GroundPathNavigation.canUpdatePath()` true, and `getNavigation().createPath(...)`
  returns a path (FOLLOW_RANGE raised to 64). The mannequin is steered along the nodes:
  * the horizontal velocity is set every tick (0.17 blocks/tick × speed);
  * it jumps (0.42) when the next node is higher or it collides horizontally;
  * a moving target is re-pathed every second;
  * no progress for 3×2 s means it is stuck.
* **Gaze while walking.** The body faces the walking direction; the head turns towards
  the look target, clamped to ±70° relative to the body.
* **Click/hit:** Fabric `UseEntityCallback` / `AttackEntityCallback` (main hand only),
  returning `SUCCESS` so vanilla handling is skipped.
* **`player_near` hysteresis:** "left" only beyond `notice_range + 1`, so standing on the
  edge doesn't flicker. Attaching a brain clears the set, so a freshly started script
  gets `player_near` for players already standing close by.
* **Protocol version 2.** The mod now accepts clients `<=` its version (the protocol only
  grows), so v0.1 scripts keep working. A v0.2 client on a v0.1 mod gets the clear old
  "mismatch" error.
* **LLM actions with JSON mode.** `response_format={"type": "json_object"}` works with
  both OpenAI and Ollama's OpenAI-compatible endpoint. Tool calling was avoided because
  `gemma3` in Ollama doesn't support tools, and JSON keeps one simple pattern for every
  backend.

### Testing

* The client game test got a **scenario mode** (`MCECA_TEST_STEPS`: chat, wait, shot,
  cmd, use, attack, walk, look, aim) so movement and clicks can be tested, not just chat.
* Interaction scenario (with `tools/test_brain.py`):
  * noticing the player;
  * all six emotions;
  * right-click with an apple (taken, held, hearts);
  * hold and give a diamond (it arrived in the player's hotbar);
  * punching;
  * `describe_surroundings()` at midnight with a cow nearby.

  The StudyLog of that run showed every event and action in order.
* Movement scenario:
  * the player teleports 10 blocks away and "Ava, come here" → `arrived` after 2.7 s;
  * follow after a teleport;
  * stop;
  * a 9×3 stone wall between them: Ava walked around it and arrived on the player's
    side in 4.5 s (the wall at x≈24, Ava ended at x≈26.9);
  * `walk_to` a position.
* Example 07 with `gemma3:4b`: the model chose `come`, `follow`, `stop` and `give_bread`
  correctly and answered with the night-time surroundings. It sometimes put an action
  name in the `gesture` field; the script ignores unknown values, and the prompt now
  describes each field.
* Example 06: greet, goodbye, greet again; gift (poppy) taken with hearts; punch.
* Example 08: log with participant `P01`, condition, every behaviour and response
  times (3.4 s for the first answer while the model loads, then 1.2 s).
* **Offline Python tests** (`python/tests`, fake mod over TCP): 7 tests incl. Ctrl+C
  closing the log, because background processes can't receive Ctrl+C in the automated
  run.

### Problems found and fixed

* Speech bubbles went dark at night (display entities use the world light): now
  `setBrightnessOverride(FULL_BRIGHT)`.
* `follow()` jittered at the edge of its distance: it now only starts walking again when
  the player is `distance + 0.75` away, using the previous tick's state. (A first
  version checked the current tick's `moving` flag, which was always false at that
  point.)
* Test harness: `tp ... facing entity` put the camera above the NPC, so right-click
  missed (out of reach). A client-side `aim` step fixed it. This was a test problem, not a
  mod problem.

### First user test (TA)

The TA ran the examples on their own world. The greeter (06) worked. Example 07 answered
everything with "Sorry, I lost my train of thought", and the terminal showed
`LLM error: Connection error.`

The cause: Ollama wasn't running. During development it had been started as a temporary
background process, which had stopped. Fixes:

* Ollama now runs as a Homebrew service (`brew services start ollama`), so it starts at
  login.
* New `mceca.check_llm(client, model)`, called at the start of every LLM example. It
  stops the script with the exact fix: start Ollama, `ollama pull <model>`, or set the
  key in `.env`. Tested against a real Ollama (ok and missing model), an unreachable
  port, and a placeholder key; unit tests added.
* Runtime LLM errors now point to `docs/04-troubleshooting.md`, which has a new section
  on this symptom.

**Lesson:** a student's first failure mode should produce a sentence telling them what
to do, not a stack trace or a polite NPC.

## 2026-10-05: Step 3 (v0.3.0): voice

### Decisions

* **No course key during development**, and many students won't have one either. So voice
  works **offline by default** (local models), with OpenAI `whisper-1` / `tts-1` as a
  one-word switch. Measured on the dev Mac (M4 Pro, Python 3.14):
  * faster-whisper `base`, int8, CPU: 3.1 s of speech → text in 0.66 s, word for word;
  * Piper `en_US-lessac-medium`: 3.9 s of audio in 0.38 s;
  * Whisper transcribing Piper's output got it back almost word for word, so the voice
    is clear.
* All packages (sounddevice, numpy 2.5, faster-whisper 1.2.1 + ctranslate2 4.8,
  piper-tts 1.8 + onnxruntime 1.30) install as wheels on Python 3.14 (macOS arm64).
* **Gotcha:** faster-whisper's file decoder calls PyAV with an argument newer PyAV
  removed (`metadata_errors`). We never pass files: the audio goes in as a numpy
  array, which avoids PyAV completely.
* **Push-to-talk in Minecraft**, not a global hotkey in Python (which would need OS
  accessibility permissions and a focus trick). This needs a small **client** part of the
  mod: a `KeyMapping` (V) and a `CustomPacketPayload` sent with Fabric networking.
  Players on a server without the mod simply can't use voice.
* **Audio stays in Python.** Minecraft only sends "pressed/released", and the script
  records the laptop's microphone. That keeps the mod simple, and both backends work the
  same way. The cost: script and game must run on the same computer, and the voice
  isn't 3D (it comes from the laptop speakers).
* **Spoken input goes into `on_chat`** (with `player.spoke`), so every existing agent
  understands voice without changes.
* `voice_start`/`voice_end` are handled **on the connection thread** (recording has to
  start immediately, even if a handler is waiting for an LLM), and transcription runs
  on a worker thread. `_call()` is never used on the connection thread, because it would
  wait for a reply that only that thread can read.
* `say()` makes the audio first and then shows the bubble, so text and voice start
  together. The thinking bubble stays up during synthesis.
* **Barge-in** (`interruptible=True`): pressing V stops the NPC's speech.
* The speech packages are an extra (`pip install -e "python[voice]"`), imported only
  when a `Voice` is created, so `mceca` itself still needs nothing.

### Testing

* New test steps `talk_start` / `talk_end` hold the real V key in the client.
  `MCECA_FAKE_MIC` replaces the microphone with a wav file made with macOS `say`;
  `MCECA_TTS_OUT` saves what the NPC says.
* End-to-end in the game with example 09 (Ollama `gemma3:4b`, local voice):
  1. The action bar showed "● Ava is listening… release the key to send".
  2. The chat showed `<Player0> [voice] Ava, can you come here please? I want to show you something.`
  3. The handler got it with `spoke=True`.
  4. The LLM answered, and the bubble and voice played together.
  5. Transcribing the saved audio gave back "Hi there, hold V and talk to me." and
     "Of course, let's go. What have you found?"
* Error paths in the game: "Nobody is close enough to hear you" (too far), and
  "Ava can't hear voice: create it with NPC(..., voice=Voice())" (script without
  voice).
  * **Fixed:** that hint was first sent on key *press* and got overwritten by the
    "working out what you said" message on release; it's now sent on release.
* Unit tests: 16 in total (voice plumbing, OpenAI request format with a fake client).
* **Flaky harness hang (once):** see building-the-mod.md, "If a test run hangs".
* **Not tested:** OpenAI voice with a real key (the request format is unit-tested);
  Windows; a real microphone (needs a person; the fake mic covers everything after
  the recording).

## 2026-10-06: v0.4.0: agents that hear each other + the all-in-one agent

### Why A2A at all

Multi-party interaction is an HAI topic in its own right:
* who speaks when;
* how the human knows who is addressed;
* whether agents look at the speaker;
* whether a second agent makes the first one more believable.

It also enables hand-overs (a guide passes the player to a shopkeeper) and lets agents
from different groups meet in one world. Google's "A2A protocol" (connecting AI
services to each other) was considered out of scope; what matters here is agents
hearing each other in the world.

### Design

* **Mod:** after every `say`, NPCs with a brain within `hearing_range` of the speaker
  get `npc_said` with `speaker`, `text`, `distance`, `addressed` (the sentence starts
  with their name, same rule as player chat) and `chain`.
* **Loop guard across scripts.** The danger is two agents answering each other forever.
  A guard inside one script can't see replies made by another script, so the count
  travels with the sentence:
  * `say` carries `chain`, and the mod copies it into `npc_said`;
  * the Python library sets a "current chain" (incoming + 1) while an `on_npc_say`
    handler runs, and `say()` sends that value;
  * listeners ignore `npc_said` with `chain >= max_npc_turns`;
  * player messages and timers start at 0, and `mceca.after()` keeps the chain it was
    scheduled with, so a delayed reply can't escape the guard.

  Unit test: two NPCs that each answer everything stop after exactly 3 replies.
* **`look_at` another NPC** (`target_npc`): the look target became an `Entity` instead
  of a `ServerPlayer`. Listeners look at whoever is talking.
* `walk_to(player)` default distance 2 → 3 blocks. In the showcase test the agent
  walked up to 2 blocks, which put its speech bubble out of view and felt too close.
  3 blocks matches the spawn and follow distances.

### Example 10: the all-in-one agent

Built around **sense → think → act**:
* every event becomes an English observation;
* one `think()` asks the LLM for a JSON decision (say, gesture, emotion, action, item),
  with the persona, `describe_surroundings()` and the memory per player;
* one `act()` validates and executes it.

Students get one place to extend instead of many separate handlers.

Test with `gemma3:4b` and local voice (fake mic), one long scenario:

| Observation | Decision |
|-------------|----------|
| player walks up | wave + happy, a greeting |
| typed "what is this place like?" | an answer about the plains, from its perception |
| spoken "can you come here?" (6 blocks away) | `come`, and it walked over |
| "I'm so hungry" | `give` apple |
| player offers a poppy | `take`, love, "Oh, how lovely!" (the persona loves flowers) |
| punch | angry + shake, "Ouch! That wasn't very kind." |
| midnight, "is it safe?" | mentioned the dark |

All 9 replies were also spoken (saved audio). The model once invented an emotion
("concerned"); `act()`'s validation skipped it.

### Example 11: two agents

Ava (guide, can't sell) and Bob (merchant, can `give` from a list). Test: *"Ava, I'm
really hungry"* → Ava: *"Bob, the player needs some food…"* → Bob (addressed) answered
the player and gave them an apple, while Ava turned to look at Bob.

The model wrote "He's feeling a bit peckish" about the player. Both personas now ask
the model to call the player "the traveller"/"they" and not to guess their gender.

## 2026-10-06: v0.4.1: first long session by the TA, diagnosis and fixes

**Report:** example 10 "worked amazing for a while" and then stopped answering. Later,
in example 11 (no voice yet), pressing V showed *"Ava can't hear voice…"*, which was
correct behaviour but confusing.

**Diagnosis from the logs:**
* **Minecraft log:** 4 minutes of good conversation, voice included. From 00:21:12
  there was 30 s of silence. Then one answer arrived **5 s** after the LLM had finished,
  which is exactly the library's reply timeout, so the connection thread had stopped
  reading replies. After that, "hi" and "yeah" were never answered.
* **Ollama log:** no LLM request at all after 00:21:37, so the agent's main thread was
  stuck too.
* **Most likely cause:** sound-device calls on two threads at once. Push-to-talk opened
  and closed the microphone *on the connection thread*, while the main thread started
  playback with `sounddevice.play()`. CoreAudio can block in that situation, and the
  Mac also had an iPhone (Continuity) microphone that comes and goes. That freezes the
  connection thread (missed replies, 5 s timeouts) and then the main thread.
* **Second possible cause:** an uncaught exception in a handler would also have ended
  the script. The terminal output wasn't available to tell which it was.
* **Also visible:** LLM latency grew from 3.3 s to 5.4 s over the session as the history
  grew (24 messages plus a long system prompt).

**Fixes:**
1. **One audio thread.** Every sound-device call (open/close microphone, output) runs on
   one daemon thread.
   * The connection thread only queues "start listening".
   * Stopping and transcribing happen on a worker thread, which waits for the audio
     thread with a 10 s limit.
   * Output is one continuously open `OutputStream` fed from a queue (resampled to the
     device rate), so `play()` returns in under 1 ms, sentences play in order (also
     across NPCs), and barge-in clears the queue.
   * A generation counter also drops sentences that were still on their way to the
     queue.
   * Verified on the real speakers (real-time draining) and with unit tests.
2. **`_guarded()`:** any exception in a handler or timer is printed with a traceback, and
   the agent keeps running (unit test: a crash on one message, the next one is still
   handled).
3. **Watchdog thread:** after 20 s in one handler it prints the handler name and the
   main thread's stack (unit test checks that it shows the blocking line).
4. **`clean_reply()`:** while testing example 11 with voice, gemma3 leaked
   `…I'll wait here."} ```json {` into a sentence. The helper strips such leftovers;
   9 real and tricky cases are in the unit tests.
5. **Example 10:** memory 24 → 12 messages; no repeated LLM greeting within 30 s.
6. **Example 11:** voice (Ava `lessac`, Bob `ryan`); the Whisper model is shared.
7. **`MCECA_PORT`:** lets the automated test run on port 25600 while the TA's game uses
   25599. All tests for this release ran next to the TA's open game without touching it.

**Re-tested:**
* Example 11 with voice: hand-over, push-to-talk to Ava, both voices (5 utterances).
* Example 10 regression: greeting, question, spoken request, gift, punch (6
  utterances).
* 22 unit tests.

## 2026-10-06: v0.5.0: packaging

The TA confirmed a long session works with the developer client (`gradlew runClient`).
The real student path (official launcher, Prism, Modrinth App) was still untested, so
packaging focused on making that path simple:

* **One-click pack (.mrpack).** Students otherwise have to install Fabric, find the right
  Fabric API and copy jars by hand. The Modrinth pack format is understood by Prism
  Launcher and the Modrinth App and creates a **separate instance**.
  * Contents: `modrinth.index.json` (Minecraft 26.3, Fabric Loader 0.19.5, Fabric API
    0.161.0+26.3 as a Modrinth CDN download with sha1/sha512), `overrides/mods/mc-eca.jar`,
    and an `overrides/options.txt` with `pauseOnLostFocus:false`.
  * `tools/make_mrpack.py` downloads Fabric API once and checks it against Modrinth's
    hashes. The Modrinth file is byte-identical to the one the mod was built and tested
    with (same sha1 as in the Gradle cache).
* **Official launcher pitfall:** all launcher installations share one `mods` folder by
  default, and the TA's launcher also has 1.21.11 and a 26.1 snapshot. Putting a
  26.3-only mod there would break the other versions, so the guide now has students give
  the Fabric installation its **own game directory**.
* **GitHub Actions:**
  * CI builds the mod and runs the Python tests on ubuntu/macos/windows ×
    Python 3.10/3.14. That is the only Windows coverage for now; a Windows laptop with
    Minecraft is still untested.
  * Release workflow on `v*` tags (checks tag = `mod_version`, builds jar + pack, uses
    `gh release create` with the CHANGELOG section). Action versions are the newest
    majors as of today (checkout v7, setup-python v7, setup-java v6, setup-gradle v6,
    upload-artifact v7); linted with `actionlint`.
* **Python 3.10 minimum.** 3.9 has been end-of-life since Oct 2025. The suite was run
  locally on 3.10 (via `uv`) and 3.14. On machines without audio libraries, the test
  that needs `sounddevice` skips, and the Ctrl+C test skips on Windows (no way to send
  SIGINT to a child process there).
* **Hygiene:** scanned for keys and personal data (only the dummy `api_key="ollama"`).
  The tracked files are sources, docs, images and the Gradle wrapper jar; `dist/`,
  `logs/`, `.env`, `mod/run/` (the TA's test worlds) and build output are ignored.
* Install guide rewritten (two ways, Windows notes), one-page handout, issue template.

## 2026-10-06: published

* Public repository: <https://github.com/Mankiwtsu/mc-eca>. First release **v0.5.0** with
  `mc-eca-0.5.0.jar` and `mc-eca-0.5.0.mrpack`, built by the release workflow.
* First CI run green: mod build, plus Python tests on ubuntu/macos/windows × 3.10/3.14
  (Windows: 22 tests, 2 skipped by design).
* The release workflow also *updates* an existing release when its tag is pushed again
  (e.g. moved to a fixed commit), instead of failing.

## Next steps (planned)

1. A real run-through of the student path: import the pack in Prism Launcher or the
   Modrinth App (and/or follow Way B), then examples 01 and 09.
2. A Windows laptop run-through.
3. When a course key is available: run the examples with `"openai"`.
