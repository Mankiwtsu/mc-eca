# MC-ECA: build your embodied conversational agent in Minecraft

*Human-Agent Interaction: an alternative to the NAO robot, Unity or Godot for your project.*

**What it is.** A character in Minecraft (the *body*) that you program in Python (the
*brain*), just like the robot: `npc.say(...)`, `npc.gesture("nod")`, `npc.look_at(player)`.
It can talk in a speech bubble or out loud, listen to your voice, look, gesture, show
emotions, walk and follow, hand over items, notice what players do, and talk with other
agents. An LLM (the course OpenAI key, or a free local model) can decide what it says
and does.

**What you need.** One laptop per group with **Minecraft: Java Edition**, **Python 3.10+**,
and about 15 minutes. No Java programming, and no cost beyond Minecraft: free local AI
models are included.

## Get started

1. **Download** the MC-ECA repository (*Code → Download ZIP*) and, from its *Releases* page,
   `mc-eca-<version>.mrpack`.
2. **Minecraft:** import the `.mrpack` in [Prism Launcher](https://prismlauncher.org) or the
   [Modrinth App](https://modrinth.com/app), start it and create a world (Creative, Superflat).
3. **Python**, in the repository folder:
   `python -m venv .venv`, activate it, `pip install -e python -r examples/requirements.txt`
4. **Run** `python examples/01_hello.py`. Ava appears in front of you. Press **T** and say hi.

Step-by-step with screenshots: `docs/01-install.md`. The tutorial is
`docs/02-your-first-agent.md`.

## Pick your modality

Your pilot study needs verbal dialogue **plus one additional modality**. Each one is a
function call you can switch on or off per condition:

| Modality | Call | Example |
|----------|------|---------|
| Gaze | `npc.look_at(player)` | looks at you vs. looks around |
| Gestures | `npc.gesture("nod")` | LLM-chosen gestures vs. none |
| Emotions | `npc.emote("happy")` | emotion display vs. none |
| Proxemics | `npc.walk_to(player, distance=…)`, `npc.follow(...)` | approaches you vs. waits |
| Objects | `npc.give(...)`, `npc.take(...)` | hands you items vs. only talks |
| Voice | `NPC(..., voice=Voice())` | spoken vs. written answers |
| Multi-party | `on_npc_say`, a second NPC | one agent vs. two agents |

Start from an example: `05` (LLM picks gestures), `07` (LLM decides actions),
`08` (**pilot-study template** with conditions and logging), `09` (voice), `10` (everything).

## Rules

* **API key:** request it from the course coordinator. Put it only in the `.env` file,
  never in your code or on GitHub.
* **Participants' data:** `StudyLog` writes CSV logs without Minecraft usernames. Ask
  participants not to type personal details, and **delete all logs when the course ends**.
* **AI coding assistants** are allowed. Give them `AGENTS.md` from the repository.

## Help

`docs/04-troubleshooting.md` covers the common problems. Bring the output of `/eca status`
(in Minecraft) and your terminal output when you ask your TA.
