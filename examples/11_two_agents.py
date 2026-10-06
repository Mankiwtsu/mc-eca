"""
Example 11 - two agents that hear each other (agent-to-agent, multi-party).

Ava is a village guide, Bob is the merchant standing next to her. Both are LLM
agents, and both hear what the other one says:

  You:  "Ava, I'm hungry and I'd like to buy something."
  Ava:  "Bob, this traveller is hungry, could you help them?"   (Ava addresses Bob)
  Bob:  "Of course! Here's a fresh loaf of bread for you."     (Bob hears he was addressed,
                                                                 answers you and gives bread)

While someone talks, the others look at the speaker (multi-party gaze).
max_npc_turns stops the two from talking to each other forever.
With VOICE on, both speak out loud with different voices, and you can talk to the
one closest to you by holding V.

Run (with Minecraft open in a world):
    python examples/11_two_agents.py
Walk up to them and talk to Ava (start with "Ava," or stand closest to her).

Set BACKEND to "openai" (course key in .env) or "ollama" (free, local).
"""

import json

from dotenv import load_dotenv
from openai import OpenAI

import mceca
from mceca import NPC, check_llm, clean_reply, Voice

BACKEND = "ollama"  # or "openai"
VOICE = "local"     # "local", "openai" or None (text only); needs pip install -e "python[voice]"

load_dotenv()
if BACKEND == "openai":
    client, MODEL, EXTRA = OpenAI(), "gpt-5-nano", {"reasoning_effort": "minimal"}
else:
    client, MODEL, EXTRA = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama"), "gemma3:4b", {}
check_llm(client, MODEL)

WARES = ["bread", "apple", "torch", "map"]

AVA = """You are Ava, a friendly village guide in a Minecraft world. Bob, the merchant,
stands right next to you. You only give directions and advice; you don't sell or give
anything. When the player wants to buy, trade or get an item, or is hungry, hand them
over to Bob: start your answer with "Bob," and tell Bob briefly what the player needs.
Call the player "the traveller" or "they"; don't guess their gender.
Reply ONLY with a JSON object: {"say": "<one or two short sentences>"}"""

BOB = f"""You are Bob, a cheerful merchant in a Minecraft village, standing next to Ava,
the guide. You can give the player one of these items: {", ".join(WARES)}. Talk to the
player, not to Ava. Don't guess the player's gender. Reply ONLY with a JSON object:
{{"say": "<one or two short sentences>", "give": "<one of {WARES} or none>"}}"""

if VOICE == "openai":
    ava_voice, bob_voice = Voice(stt="openai", tts="openai", openai_voice="nova"), Voice(stt="openai", tts="openai", openai_voice="onyx")
elif VOICE == "local":
    ava_voice, bob_voice = Voice(piper_voice="en_US-lessac-medium"), Voice(piper_voice="en_US-ryan-medium")
else:
    ava_voice = bob_voice = None

ava = NPC("Ava", skin="alex", voice=ava_voice, max_npc_turns=2)
bob = NPC("Bob", skin="steve", voice=bob_voice, max_npc_turns=2)
history = {"Ava": [], "Bob": []}


def ask(npc, persona, message):
    """One LLM turn for `npc`; `message` is what it just heard. Returns the JSON reply."""
    history[npc.name].append({"role": "user", "content": message})
    try:
        response = client.chat.completions.create(
            model=MODEL, messages=[{"role": "system", "content": persona}] + history[npc.name][-16:],
            response_format={"type": "json_object"}, **EXTRA)
        raw = response.choices[0].message.content
        decision = json.loads(raw)
    except Exception as e:
        print("LLM error:", e, "(see docs/04-troubleshooting.md)")
        return {"say": "Sorry, I lost my train of thought."}
    history[npc.name].append({"role": "assistant", "content": raw})
    return decision


def nearest_player(npc):
    players = sorted(npc.players(), key=lambda p: p.distance)
    return players[0] if players else None


# ------------------------------------------------------------------- Ava

@ava.on_chat
def ava_reply(player, text):
    ava.look_at(player)
    bob.look_at(ava)            # Bob looks at Ava while she is being talked to
    ava.thinking(True)
    decision = ask(ava, AVA, f"The player says: {text}")
    print("Ava ->", decision)
    ava.say(clean_reply(decision.get("say")) or "...")


@ava.on_npc_say
def ava_hears(speaker, text):
    ava.look_at(speaker)        # listeners look at whoever speaks


# ------------------------------------------------------------------- Bob

def bob_turn(player, message):
    bob.thinking(True)
    decision = ask(bob, BOB, message)
    print("Bob ->", decision)
    if player is not None:
        bob.look_at(player)
    bob.say(clean_reply(decision.get("say")) or "...")
    item = str(decision.get("give", "none")).lower()
    if item in WARES and player is not None:
        bob.give(player, item)


@bob.on_chat
def bob_reply(player, text):
    ava.look_at(bob)
    bob_turn(player, f"The player says: {text}")


@bob.on_npc_say
def bob_hears(speaker, text):
    bob.look_at(speaker)
    if speaker.addressed:       # only answer when Ava talks *to* Bob ("Bob, ...")
        bob_turn(nearest_player(bob), f"{speaker.name} says to you: {text}")


@ava.on_player_near
def welcome(player):
    ava.look_at(player)
    bob.look_at(player)
    ava.say("Welcome to our village! I'm Ava, and this is Bob, our merchant.")


mceca.run()
