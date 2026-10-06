# 04 – Troubleshooting & tips

## The script keeps printing `waiting for Minecraft on 127.0.0.1:25599`

* Is a **world open**? The connection only exists while you are *in* a world (not in
  the main menu).
* Did you start the **MC-ECA** instance (Prism / Modrinth App) or the **fabric-loader-26.3**
  installation (official launcher), and are `fabric-api` and `mc-eca` in *its* `mods`
  folder? In a world, `/eca status` must be a known command.
* Type `/eca status` in the game. If it says `bridge failed: cannot listen on ...`,
  another program (or a second Minecraft) uses port 25599. Close it, or change `port` in
  the [config](03-api-reference.md#configuration) and use `NPC("Ava", port=...)`.

## `cannot spawn Ava yet: no player in the world yet`

The script started before you were in the world. It retries by itself; join the world.

## Minecraft says *"Ava has no brain connected – start your Python script"*

You talked to an NPC but no script controls it. Start (or restart) your script. It
reconnects to the existing Ava.

## Ava doesn't react when I type

* Stand closer: the hearing range is **8 blocks**, or start your message with her name:
  `Ava, hello`.
* Messages starting with `/` are commands, not chat.
* Is the script still running? Look for errors in the terminal.
* Is the game paused (Esc menu, or you clicked another window)? The NPC freezes while
  the game is paused. Press **F3 + P** to turn off *Pause on lost focus*.

## The NPC answers, but very slowly

* **Ollama:** the first answer after starting is slow (the model is loaded into memory).
  On older laptops use a smaller model: `ollama pull gemma3:1b` and set
  `MODEL = "gemma3:1b"`.
* **OpenAI:** keep `reasoning_effort="minimal"`. Without it, `gpt-5-nano` "thinks" first,
  which can take several seconds.
* Keep the persona's answers short; long answers also take longer to generate.

## The NPC only says "Sorry, I lost my train of thought."

Your script can't reach the AI model. The examples check this at start-up and stop
with `[mceca] LLM not ready: ...` plus the fix. If the LLM disappears while the
script runs (e.g. Ollama was closed), you see `LLM error: Connection error.` in the
terminal. Start Ollama again:

* **Ollama app** (Windows / macOS): open it; it runs in the menu bar / system tray.
* **Homebrew on macOS:** `brew services start ollama` (keeps running and starts at login;
  `brew services stop ollama` to stop it).
* **Any system:** `ollama serve` in a separate terminal, and leave that terminal open.

Check it's running: open <http://localhost:11434> in a browser; it says
"Ollama is running".

## The NPC worked for a while and then stopped answering

Look at the terminal where your script runs:

* **A traceback ("error in Ava's chat handler (the agent keeps running)")**: a bug in your
  code (or an unexpected LLM answer) for one message. The agent keeps going; fix the
  line shown.
* **"… has been running for 20 s; new events wait meanwhile. It is currently here: …"**:
  one handler is stuck (often a slow or hanging LLM call). The lines below show where.
  Everything that happens meanwhile is answered later, all at once.
* **"no answer from Minecraft for say()"**: the game was paused (Esc menu, or another
  window had focus with *Pause on lost focus* on). Press **F3 + P**.
* **Nothing at all and Ava shows "○ no brain"**: the script ended. Start it again.

Answers getting **slower** during a long conversation is normal with local models: the
whole recent conversation is sent each turn. Keep the history short (`MEMORY` /
`MAX_TURNS` in the examples), or use a smaller model.

## LLM errors in the terminal

| Message contains | Fix |
|------------------|-----|
| `api_key` / `401` / `Incorrect API key` | Check `.env`: `OPENAI_API_KEY=...` with no quotes or spaces, file in the repository folder. |
| `Connection error` / `Connection refused` + port `11434` | Ollama isn't running, see above. |
| `model "gemma3:4b" not found` | `ollama pull gemma3:4b` |
| `Unsupported parameter` / `reasoning_effort` | You use a model that doesn't support it. Remove that argument. |

## `ModuleNotFoundError: No module named 'mceca'` (or `openai`)

Your virtual environment isn't active. Run `source .venv/bin/activate` (macOS/Linux) or
`.venv\Scripts\activate` (Windows) in this terminal, then try again. If needed, repeat
`pip install -e python -r examples/requirements.txt`.

## Minecraft doesn't start / crashes on start

* Use exactly **Minecraft 26.3** (the MC-ECA instance, or the **fabric-loader-26.3**
  installation).
* Your *other* Minecraft versions crash since installing? The 26.3 mods are in their
  `mods` folder too: give the 26.3 installation its own game directory
  ([Install, Way B step 3](01-install.md#way-b-the-official-minecraft-launcher)), or use the
  one-click pack, which always makes a separate instance.
* Fabric API must be the build **for 26.3**.
* Remove other mods to test.
* The crash report is in `.minecraft/crash-reports/`. Send it to your TA.

## The speech bubble is cut off at the top of the screen

You are standing very close. Step back a little or look up. Keep answers short (one or
two sentences); the persona in the examples asks for that.

## The NPC doesn't walk where I want / `on_stuck` is called

* It uses Minecraft's pathfinding (up to ~64 blocks), walks around walls and up
  one-block steps, but **can't open doors, climb ladders or swim well**. Open doors or
  use open doorways; keep paths on land.
* `walk_to((x, y, z))`: get coordinates with **F3** (the "Block:" line) and stand on the
  target to read them. `y` is the height of the floor the NPC should stand on.
* Following stops when the player is closer than `distance`; that's on purpose.

## Right-clicking the NPC does nothing

You must be within reach (about 3 blocks) and aim at the NPC's body. Check that your
script registered `@npc.on_click`. Without a running script you get the
"no brain connected" message instead.

## Where are my study logs?

In a `logs/` folder next to where you started the script (the terminal's current
folder), named `<date>_<time>_<participant>_<condition>.csv`. The script prints the path
at the start (`[mceca] logging to ...`). `logs/` is excluded from git on purpose.

## Voice problems (V key, microphone, no sound)

See the table at the end of **[06 – Voice](06-voice.md#troubleshooting-voice)**.

## There are two Avas / an old NPC I don't want

`/eca remove Ava` deletes one. `/eca list` shows all NPCs that are loaded.

## Wizard of Oz on two laptops

Typing on the same laptop as the participant steals the game's focus. Better: the
participant plays on **laptop A**, the wizard runs `04_wizard_of_oz.py` on **laptop B**.

1. On laptop A, close Minecraft and edit `.minecraft/config/mceca.json`:
   `"bind_address": "0.0.0.0"`. Start Minecraft and open the world.
2. Find laptop A's IP address (Windows: `ipconfig`; macOS: System Settings → Wi-Fi →
   Details), e.g. `192.168.1.20`.
3. On laptop B, change the NPC line in the script:
   ```python
   npc = NPC("Ava", skin="alex", host="192.168.1.20")
   ```
4. Both laptops must be on the same network. University Wi-Fi (eduroam) usually blocks
   connections between laptops; use a phone hotspot instead. You may also have to allow
   Java through the firewall on laptop A.

Set `bind_address` back to `127.0.0.1` afterwards: while it's `0.0.0.0`, anyone on that
network could control your NPC.

## Still stuck?

Run `/eca status` and `/eca list`, copy the terminal output of your script, and ask
your TA. If you use an AI assistant, give it [`AGENTS.md`](../AGENTS.md) and the error
message.
