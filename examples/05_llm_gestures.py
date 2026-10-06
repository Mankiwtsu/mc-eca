"""
Example 5 - the LLM chooses a gesture with every answer.

The course asks for verbal dialogue plus one more modality. Here the model
starts each answer with a gesture tag, e.g.

    [nod] Yes, the village is just over that hill!

The script removes the tag, plays the gesture and says the rest.

Run (with Minecraft open in a world):
    python examples/05_llm_gestures.py

Set BACKEND below to "openai" (course key in .env) or "ollama" (free, local).
"""

import re

from dotenv import load_dotenv
from openai import OpenAI

from mceca import NPC, check_llm, clean_reply

BACKEND = "ollama"  # or "openai"

if BACKEND == "openai":
    load_dotenv()
    client = OpenAI()
    MODEL = "gpt-5-nano"
    EXTRA = {"reasoning_effort": "minimal"}
else:
    client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    MODEL = "gemma3:4b"
    EXTRA = {}

check_llm(client, MODEL)  # stops with a clear message if the LLM can't be used

GESTURES = ["nod", "shake", "wave", "crouch", "jump"]

PERSONA = f"""You are Ava, a friendly guide who lives in this Minecraft world.
Reply only with the words Ava says out loud, one or two short sentences, no emojis.
Start every reply with exactly one gesture tag that fits what you say:
[nod] agreeing or confirming, [shake] disagreeing or saying no, [wave] greeting or
saying goodbye, [crouch] excited, [jump] very happy, [none] no gesture.
Example: [wave] Hello there, traveller!"""

TAG = re.compile(r"^\s*\[(\w+)\]\s*")

npc = NPC("Ava", skin="alex")
histories = {}


@npc.on_chat
def reply(player, text):
    npc.look_at(player)
    npc.thinking(True)

    history = histories.setdefault(player.name, [])
    history.append({"role": "user", "content": text})
    messages = [{"role": "system", "content": PERSONA}] + history[-20:]

    try:
        response = client.chat.completions.create(model=MODEL, messages=messages, **EXTRA)
        answer = response.choices[0].message.content.strip()
    except Exception as e:
        print("LLM error:", e, "(see docs/04-troubleshooting.md)")
        npc.thinking(False)
        npc.say("Sorry, I lost my train of thought.")
        return

    history.append({"role": "assistant", "content": answer})

    # Split "[nod] Yes!" into the gesture and the words.
    gesture = None
    match = TAG.match(answer)
    if match:
        gesture = match.group(1).lower()
        answer = answer[match.end():]
    print(f"{player.name}: {text}\n  -> gesture={gesture}  say={answer!r}")

    if gesture in GESTURES:
        npc.gesture(gesture)
    npc.say(clean_reply(answer))


npc.run()
