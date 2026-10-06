# Building the mod (TAs / maintainers)

Students never need this: they download the finished `.jar`. This page is for whoever
maintains MC-ECA: building it, testing it, releasing it, and updating it to a new
Minecraft version.

## Toolchain

| Tool | Version | Why |
|------|---------|-----|
| JDK | **25** | Minecraft 26.x requires Java 25 |
| Gradle | 9.7.1 (downloaded by `./gradlew`) | build tool |
| Fabric Loom | 1.18 | Gradle plugin that sets up Minecraft for modding |
| Python | 3.10+ | the `mceca` library and test brains |
| Ollama *(optional)* | any | free local LLM for testing the examples |

Install on macOS with Homebrew:

```bash
brew install openjdk@25 ollama
```

`openjdk@25` is *keg-only*: it is not on your `PATH`. Either point Gradle at it per
command (`export JAVA_HOME=/opt/homebrew/opt/openjdk@25`) or add that line to `~/.zshrc`.
On Windows/Linux install [Temurin 25](https://adoptium.net/) and set `JAVA_HOME`.

## Project layout

```
mod/
├── build.gradle            Loom setup, dependencies, gametest config
├── gradle.properties       ← Minecraft / Fabric versions live here
├── src/main/java/io/github/mceca/
│   ├── McEca.java          entry point: registers events, starts/stops the bridge
│   ├── client/McEcaClient.java   client part: the push-to-talk key (V) -> PushToTalkPayload
│   ├── voice/PushToTalkPayload.java   client -> server "talk key pressed/released"
│   ├── Config.java         config/mceca.json
│   ├── EcaCommand.java     /eca status | list | remove
│   ├── bridge/             TCP server + JSON protocol (one thread pair per script)
│   │   ├── Bridge.java
│   │   ├── BridgeClient.java
│   │   ├── Json.java
│   │   └── CommandException.java
│   └── npc/
│       ├── NpcManager.java     all NPCs, command routing, chat/click/hit routing, spawning
│       ├── NpcController.java  one NPC: gaze, gestures, emotions, speech bubble, items,
│       │                       noticing players (runs every tick)
│       ├── NpcMovement.java    walking: pathfinding with a hidden helper mob + steering
│       ├── Surroundings.java   what the NPC perceives (JSON for the brain)
│       └── ItemNames.java      "apple" <-> Minecraft items
├── src/main/resources/
│   ├── fabric.mod.json
│   ├── mceca.classtweaker   opens a few private Minecraft setters (see below)
│   └── assets/mceca/lang/en_us.json   key binding names
└── src/gametest/           automated in-game test (not shipped in the jar)
```

### Design in one paragraph

The NPC body is the vanilla **mannequin** entity (added in Minecraft 1.21.9): a
player-shaped entity with a skin and no AI. Because it has no AI, walking is done by the
mod: a never-spawned helper zombie asks Minecraft's pathfinder for a route, and the
mannequin is steered along it every tick (velocity towards the next node, a jump when
the next node is higher or it bumps into a block). The speech bubble is a vanilla **text
display** entity that follows the NPC. Because both are vanilla, the mod is needed on
the **server side only**: players joining a server running MC-ECA don't need it
installed. (In singleplayer the game runs its own internal server, so the mod is in
the client.) Everything that touches the world runs on the server thread; socket I/O
runs on separate threads and hands work over with `server.execute(...)`.

### Class tweaker

`mceca.classtweaker` makes these private Minecraft methods public:
`Mannequin.setProfile/setDescription/setHideDescription` and
`Display(.TextDisplay).setText/setLineWidth/setBackgroundColor/setBillboardConstraints/setTransformation/setPosRotInterpolationDuration/setViewRange/setBrightnessOverride`.
If a Minecraft update renames one of them, `./gradlew build` fails in the
`validateAccessWidener` task and tells you which line.

## Build

```bash
cd mod
./gradlew build
```

The jar is `mod/build/libs/mc-eca-<version>.jar`. The first build downloads and
prepares Minecraft (~1 GB, 5–20 minutes); later builds take seconds.

Optional, to browse Minecraft's source code in your IDE: `./gradlew genSources` (run it
**on its own**, not together with `build`).

## Test

### Manual: play in a development client

```bash
cd mod
./gradlew runClient
```

This starts Minecraft with the mod (offline account "Player###"). Open a world, then run
any example in another terminal: `python examples/01_hello.py`.

### Automated: client game test with screenshots

`src/gametest/java/.../NpcDemoGameTest.java` drives a real Minecraft client: it creates a
superflat world, waits (max 2 min) until a brain script has spawned an NPC, then plays
a scenario and takes screenshots.

1. Start a brain in one terminal (any example works):
   ```bash
   source .venv/bin/activate
   ```
   ```bash
   python tools/test_brain.py
   ```
   `tools/test_brain.py` reacts to keywords (gestures, emotions, `think`, `come`,
   `follow`, `stop`, `east`, `look there`, `hold`, `give`, `where`) and to every event, and
   writes a StudyLog to `logs/`, so one run checks everything.
2. Run the test in another terminal, either with plain messages:
   ```bash
   cd mod && MCECA_TEST_MESSAGES="Wave at me|Can you nod?|Please think about it" ./gradlew runClientGameTest
   ```
   or with a scenario (`MCECA_TEST_STEPS`, steps separated by `|`):

   | Step | Does |
   |------|------|
   | `chat:TEXT` | the player says TEXT |
   | `wait:TICKS` | wait (20 ticks = 1 s) |
   | `shot:NAME` | screenshot |
   | `cmd:COMMAND` | server command without `/`, e.g. `cmd:execute as @p at @s run tp @s ~10 ~ ~` |
   | `aim` | point the camera at the nearest NPC (needed before `use`/`attack`) |
   | `use` / `attack` | right-click / punch what the crosshair points at |
   | `walk:TICKS` | hold the forward key |
   | `look:YAW,PITCH` | turn the camera |
   | `talk_start` / `talk_end` | press / release the push-to-talk key (V) |

   Example (movement test from the dev log):
   ```bash
   cd mod && MCECA_TEST_STEPS="wait:40|cmd:execute as @p at @s run tp @s ~10 ~ ~|wait:20|chat:Ava, come here|wait:120|shot:arrived" ./gradlew runClientGameTest
   ```
   Note that `runCommand` runs as the server, so `~` is relative to the world spawn
   unless you use `execute as @p at @s run ...`.
3. Screenshots: `mod/build/run/clientGameTest/screenshots/` (wiped at the start of each
   run). Log: `mod/build/run/clientGameTest/logs/latest.log`. NPC chat lines appear there
   as `[CHAT] <Ava> ...`, and at the end the test runs `/eca status` and `/eca list`.
   The brain's StudyLog in `logs/` shows every event/action with timing, which is the
   quickest way to check a scenario.

**Testing next to a running game:** set `MCECA_PORT=25600` for both the test game and the
brain script (e.g. `MCECA_PORT=25600 python tools/test_brain.py`, then
`MCECA_PORT=25600 ./gradlew runClientGameTest`). Your normal game keeps port 25599.

Other test brains: `tools/test_two_npcs.py` (two NPCs, name routing, bubble turn-taking,
username skin).

**Testing voice without speaking:** environment variables for the brain script:

| Variable | Effect |
|----------|--------|
| `MCECA_FAKE_MIC=/path/to/speech.wav` | "record" this file instead of the microphone |
| `MCECA_TTS_OUT=/some/folder` | save every spoken sentence as a wav file |
| `MCECA_MUTE=1` | don't play audio |

A test sentence can be made on macOS with
`say -o speech.aiff "Ava, can you come here please?" && afconvert -f WAVE -d LEI16@16000 speech.aiff speech.wav`.
Example:

```bash
MCECA_FAKE_MIC=speech.wav MCECA_MUTE=1 MCECA_TTS_OUT=tts_out python examples/09_voice_agent.py
```
```bash
cd mod && MCECA_TEST_STEPS="wait:80|talk_start|wait:40|talk_end|wait:150|shot:answer" ./gradlew runClientGameTest
```

To check what the NPC *said*, transcribe the files in `tts_out` with faster-whisper.

**If a test run hangs at "Saving worlds":** this happened once in ~30 runs. The server
thread waited for chunk saving while the test framework waited for the client to
disconnect, and nothing from MC-ECA was on the stack. Kill the game (`jps -l`, then
`kill <pid>` of `devlaunchinjector.Main`) and run again. To get a time limit on macOS,
use `perl -e 'alarm 400; exec @ARGV' ./gradlew runClientGameTest`.

**macOS:** the test opens a real window. If the display is asleep or locked, rendering
blocks and the test hangs at startup. Run it with `caffeinate -dimsu ./gradlew
runClientGameTest` and keep the screen unlocked.

### Offline: Python unit tests

`python/tests/test_mceca.py` replaces Minecraft with a fake mod (a TCP server in the
test), so the library can be tested anywhere in two seconds:

```bash
.venv/bin/python -m unittest discover -s python/tests -v
```

It covers:
* the handshake, the JSON of every action, error handling and event dispatch;
* timers;
* StudyLog anonymisation, and that Ctrl+C closes the log;
* `check_llm`;
* the voice plumbing, with a fake voice: push-to-talk becomes a spoken chat message, the
  transcript, spoken `say()`, cancelled recordings, the "no voice" hint;
* the exact `whisper-1` / `tts-1` requests, with a fake OpenAI client;
* the NPC-to-NPC loop guard, with two NPCs and a relay standing in for the mod.

### Production check: dedicated server

To check the **built jar** (not the dev classes), run it on a real Fabric server:

```bash
mkdir server && cd server
curl -o server.jar "https://meta.fabricmc.net/v2/versions/loader/26.3/0.19.5/1.1.2/server/jar"
mkdir mods && cp ../mod/build/libs/mc-eca-*.jar <fabric-api-26.3.jar> mods/
echo "eula=true" > eula.txt
java -jar server.jar nogui
```

The log must show `MC-ECA bridge listening on 127.0.0.1:25599`. A `hello` over the
socket must answer `{"ok": true, ...}` (see the protocol in
[03-api-reference.md](../03-api-reference.md#try-it-by-hand)).

## Automatic checks (GitHub Actions)

`.github/workflows/ci.yml` runs on every push and pull request:
* it builds the mod with Java 25 (the jar is downloadable from the run, under
  *Artifacts*);
* it runs the Python tests on **Linux, macOS and Windows** with Python 3.10 and 3.14.
  The tests that need audio hardware are skipped there.

Check with `actionlint` (`brew install actionlint`) after editing a workflow.

## Release a new version

1. Bump the version in **three** places: `mod/gradle.properties` (`mod_version`),
   `python/pyproject.toml`, `python/mceca/__init__.py`.
2. If commands or events were added or changed, bump `PROTOCOL_VERSION` in
   `Bridge.java` **and** `python/mceca/client.py`, and add a line to the version list in
   `Bridge.java`. The mod accepts clients up to its own version (older scripts keep
   working); a newer client on an older mod gets a clear "update the MC-ECA mod" error.
3. Add a `## <version> – <date>` section at the top of `CHANGELOG.md`. It becomes the
   release notes.
4. Run the offline Python tests, then the automated in-game test with
   `tools/test_brain.py` and with an LLM example; look at the screenshots and the log.
5. Commit, then tag and push:
   ```bash
   git tag v0.5.0
   ```
   ```bash
   git push origin main v0.5.0
   ```
   `.github/workflows/release.yml` then:
   * checks that the tag matches `mod_version`;
   * builds the mod and the one-click pack (`tools/make_mrpack.py`);
   * creates the GitHub release with `mc-eca-<version>.jar`, `mc-eca-<version>.mrpack`
     and the changelog section.

To build the pack locally: `cd mod && ./gradlew build && cd .. && python tools/make_mrpack.py`
→ `dist/mc-eca-<version>.mrpack`. It contains the MC-ECA jar and an `options.txt` that
turns off *Pause on lost focus*. Fabric API is a checksummed Modrinth download link, and
the Fabric API version comes from `fabric_api_version` in `gradle.properties`, so keep
that one on a version that exists on Modrinth.

## Update to a new Minecraft version

Pick **one** Minecraft version per course year and don't change it mid-semester.

1. Look up the matching versions on <https://fabricmc.net/develop/> (Minecraft, loader,
   Loom, Fabric API) and put them in `mod/gradle.properties`.
2. In `fabric.mod.json`, update `"minecraft": "~26.3"` (and `java` if Mojang changed it:
   check `javaVersion` in the version JSON from Mojang's
   [version manifest](https://piston-meta.mojang.com/mc/game/version_manifest_v2.json)).
3. `./gradlew build`, fix compile errors. Since 26.1 Minecraft ships unobfuscated, so
   class and method names in errors are the real ones: search the Minecraft jar with
   `javap` or run `genSources`.
4. Run all automated tests; look at the screenshots (bubble height, gestures).
5. Update the version numbers in the student docs (`docs/01-install.md`, README).
