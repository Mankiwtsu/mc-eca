"""
Example 7 - an LLM agent that decides what to SAY and what to DO.

Every turn the model gets:
  * a persona,
  * what Ava perceives right now (time, weather, nearby players and animals), and
  * the conversation so far,
and answers with a JSON object, for example:

    {"say": "Sure, follow me to the river!", "gesture": "nod",
     "emotion": "happy", "action": "lead"}

The script then speaks, gestures, shows the emotion and carries out the action.
This "structured output" pattern is how you turn an LLM into an embodied agent.

Run (with Minecraft open in a world):
    python examples/07_llm_actions.py
Try: "Can you come here?", "Follow me!", "Stop.", "I'm hungry", "What time is it?"

Set BACKEND to "openai" (course key in .env) or "ollama" (free, local).
"""

import json

from dotenv import load_dotenv
from openai import OpenAI

from mceca import EMOTIONS, GESTURES, NPC, check_llm, clean_reply

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

# The actions the model may choose, and what they do.
ACTIONS = {
    "none": "do nothing special",
    "come": "walk over to the player",
    "follow": "keep following the player until they say stop",
    "stop": "stop walking or following",
    "give_bread": "give the player a piece of bread (when they are hungry)",
}


def do_action(action, player):
    if action == "come":
        npc.walk_to(player)
    elif action == "follow":
        npc.follow(player, distance=3)
    elif action == "stop":
        npc.stop()
    elif action == "give_bread":
        npc.give(player, "bread")


def system_prompt():
    return f"""You are Ava, a friendly and helpful villager in a Minecraft world.

What you perceive right now: {npc.describe_surroundings()}

Answer ONLY with a JSON object with exactly these keys:
  "say":     what you say out loud, one or two short sentences, no emojis
  "gesture": a body movement, one of {list(GESTURES) + ["none"]}
  "emotion": a feeling shown above your head, one of {list(EMOTIONS) + ["none"]}
  "action":  something you do in the world, one of {list(ACTIONS)}
Actions: {"; ".join(f"{name} = {what}" for name, what in ACTIONS.items())}.
Only choose an action when the player asks for it or it clearly helps them."""


npc = NPC("Ava", skin="alex")
histories = {}


@npc.on_chat
def reply(player, text):
    npc.look_at(player)
    npc.thinking(True)

    history = histories.setdefault(player.name, [])
    history.append({"role": "user", "content": text})
    messages = [{"role": "system", "content": system_prompt()}] + history[-20:]

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            response_format={"type": "json_object"},  # forces valid JSON
            **EXTRA,
        )
        raw = response.choices[0].message.content
        decision = json.loads(raw)
    except Exception as e:
        print("LLM error:", e, "(see docs/04-troubleshooting.md)")
        npc.thinking(False)
        npc.say("Sorry, I lost my train of thought.")
        return

    history.append({"role": "assistant", "content": raw})
    print(f"{player.name}: {text}\n  -> {decision}")

    gesture = str(decision.get("gesture", "none")).lower()
    emotion = str(decision.get("emotion", "none")).lower()
    action = str(decision.get("action", "none")).lower()

    if gesture in GESTURES:
        npc.gesture(gesture)
    if emotion in EMOTIONS:
        npc.emote(emotion)
    npc.say(clean_reply(decision.get("say")) or "...")
    if action in ACTIONS:
        do_action(action, player)


@npc.on_arrive
def arrived():
    npc.say("Here I am!")


@npc.on_stuck
def stuck():
    npc.emote("confused")
    npc.say("Hmm, I can't find a way to get there.")


npc.run()
