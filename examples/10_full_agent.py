"""
Example 10 - the all-in-one agent: everything MC-ECA can do, in one character.

Ava is a village guide who
  * hears you type OR talk (hold V) and answers out loud,
  * notices you arriving, leaving, handing her things and punching her,
  * knows where she is (time, weather, animals nearby, what you hold),
  * decides with an LLM what to say AND do: gesture, emotion, walk over, follow,
    stop, give or accept items,
  * glances around when nobody is there,
  * answers other NPCs that talk to her (see example 11),
  * can log the whole session for a study.

The heart is one loop. Every event becomes an OBSERVATION in plain English
("The player walks up to you."), think() turns it into a DECISION with the LLM
(a JSON object), and act() carries it out: sense -> think -> act.
To change the agent, change the observations, the persona or the actions.

Run (with Minecraft open in a world):
    python examples/10_full_agent.py
Needs the voice extras (pip install -e "python[voice]"), or set VOICE = None.
"""

import json
import random
import time

from dotenv import load_dotenv
from openai import OpenAI

import mceca
from mceca import EMOTIONS, GESTURES, NPC, check_llm, clean_reply, StudyLog, Voice

# ----------------------------------------------------------------- settings

BACKEND = "ollama"  # LLM: "ollama" (free, local) or "openai" (course key in .env)
VOICE = "local"     # speech: "local", "openai" or None (text only)
LOG = False         # True: write a StudyLog (CSV) to logs/

NAME, SKIN = "Ava", "alex"
ITEMS = ["bread", "apple", "torch", "map", "poppy"]  # what Ava can give away

PERSONA = f"""You are {NAME}, a warm and curious village guide in a Minecraft world.
You help travellers explore, you love flowers, and you don't like rudeness.
Speak directly to the player as "you" and don't guess their gender."""

ACTIONS = {
    "none": "do nothing special",
    "come": "walk over to the player",
    "follow": "follow the player until they ask you to stop",
    "stop": "stop walking or following",
    "give": f'give the player an item; put it in "item" (one of {ITEMS})',
    "take": "accept the item the player is holding out to you",
}

# -------------------------------------------------------------------- setup

load_dotenv()
if BACKEND == "openai":
    client, MODEL, EXTRA = OpenAI(), "gpt-5-nano", {"reasoning_effort": "minimal"}
else:
    client, MODEL, EXTRA = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama"), "gemma3:4b", {}
check_llm(client, MODEL)

if VOICE == "openai":
    voice = Voice(stt="openai", tts="openai", openai_voice="nova")
elif VOICE == "local":
    voice = Voice()
else:
    voice = None

log = StudyLog(condition="full-agent") if LOG else None
npc = NPC(NAME, skin=SKIN, voice=voice, log=log, notice_range=6)

MEMORY = 12       # messages sent to the LLM each turn: more = better memory but slower answers
memory = {}       # who -> the conversation so far (observations and decisions)
visitors = set()  # players standing near Ava right now
last_greeted = {} # player -> time of the last greeting (don't greet again within 30 s)


# ------------------------------------------------------------ think and act

def instructions():
    """The system prompt, rebuilt every turn so Ava knows what is around her now."""
    return f"""{PERSONA}

What you perceive right now: {npc.describe_surroundings()}

You receive observations about what happens around you. Decide how to react and
answer ONLY with a JSON object with these keys:
  "say":     what you say out loud: one or two short, natural sentences ("" = stay silent)
  "gesture": a body movement, one of {list(GESTURES) + ["none"]}
  "emotion": a feeling shown above your head, one of {list(EMOTIONS) + ["none"]}
  "action":  something you do, one of {list(ACTIONS)}
  "item":    for "give": one of {ITEMS}; otherwise "none"
Actions: {"; ".join(f"{name} = {what}" for name, what in ACTIONS.items())}.
No emojis, no lists, no stage directions."""


def think(who, observation):
    """Observation -> decision (dict), using the LLM and the memory of `who`."""
    history = memory.setdefault(who, [])
    history.append({"role": "user", "content": observation})
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": instructions()}] + history[-MEMORY:],
            response_format={"type": "json_object"},
            **EXTRA,
        )
        raw = response.choices[0].message.content
        decision = json.loads(raw)
    except Exception as e:
        print("LLM error:", e, "(see docs/04-troubleshooting.md)")
        return {"say": "Sorry, I lost my train of thought."}
    history.append({"role": "assistant", "content": raw})
    print(f"  {observation}\n  -> {decision}")
    return decision


def act(decision, player=None):
    """Carry out a decision. Every value is checked, because LLMs make mistakes."""
    gesture = str(decision.get("gesture", "none")).lower()
    emotion = str(decision.get("emotion", "none")).lower()
    action = str(decision.get("action", "none")).lower()
    item = str(decision.get("item", "none")).lower()

    if gesture in GESTURES:
        npc.gesture(gesture)
    if emotion in EMOTIONS:
        npc.emote(emotion)
    text = clean_reply(decision.get("say"))  # removes JSON/markdown leftovers small models sometimes add
    if text:
        npc.say(text)  # bubble + voice
    else:
        npc.thinking(False)

    if player is None:
        return  # talking to another NPC: no actions
    try:
        if action == "come":
            npc.walk_to(player)
        elif action == "follow":
            npc.follow(player, distance=3)
        elif action == "stop":
            npc.stop()
        elif action == "give" and item in ITEMS:
            npc.give(player, item)
        elif action == "take":
            npc.take(player)
    except mceca.McEcaError as e:  # e.g. "take" when the player's hand is empty
        print("  action failed:", e)


def respond(player, observation):
    npc.look_at(player)
    npc.thinking(True)
    act(think(player.name, observation), player)


# ------------------------------------------------------------- sense: events

@npc.on_chat  # typed, or spoken with V
def heard(player, text):
    respond(player, f'The player {"says" if player.spoke else "writes"}: "{text}"')


@npc.on_player_near
def approached(player):
    visitors.add(player.name)
    if time.time() - last_greeted.get(player.name, 0) < 30:
        npc.look_at(player)  # just stepped out and back in: no new greeting (saves an LLM call)
        return
    last_greeted[player.name] = time.time()
    respond(player, "The player walks up to you.")


@npc.on_player_leave
def left(player):
    visitors.discard(player.name)
    npc.look_at(None)
    npc.say("Safe travels!", speak=False)


@npc.on_click
def clicked(player, item):
    if item:
        respond(player, f"The player holds out a {item.replace('_', ' ')} to give to you.")
    else:
        respond(player, "The player taps you on the shoulder.")


@npc.on_hit
def punched(player):
    respond(player, "The player punched you!")


@npc.on_arrive
def arrived():
    npc.say("Here I am!")


@npc.on_stuck
def stuck():
    npc.emote("confused")
    npc.say("Hmm, I can't find a way over there.")


@npc.on_npc_say
def other_npc(speaker, text):
    npc.look_at(speaker)  # look at whoever is talking
    if speaker.addressed:  # only answer when spoken to ("Ava, ...")
        act(think(speaker.name, f'{speaker.name}, another villager, says to you: "{text}"'))


@mceca.every(8)
def idle():
    """While nobody is around, glance at a random spot now and then."""
    if visitors:
        return
    pos = npc.position()
    if pos:
        x, y, z = pos
        npc.look_at((x + random.uniform(-8, 8), y + random.uniform(0.5, 2.5), z + random.uniform(-8, 8)))


print(f"{NAME} is ready: walk up to her, type in the chat, or hold V and talk.")
mceca.run()
