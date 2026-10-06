"""
Example 8 - a template for running a pilot study.

It runs one session with one participant in one condition and writes a
log file (CSV) you can analyse afterwards in Excel, pandas or R.

    python examples/08_pilot_study.py --participant P01 --condition expressive
    python examples/08_pilot_study.py --participant P02 --condition neutral

The two conditions here differ in the non-verbal behaviour only:
  expressive: Ava looks at the participant, shows a thinking bubble, nods and
              shows emotions chosen by the LLM
  neutral:    the same words, but no gaze, no thinking bubble, no gestures
Change CONDITIONS to whatever your study compares.

The log (logs/<date>_<participant>_<condition>.csv) contains every message,
every behaviour and the response time of each answer, without Minecraft
usernames. Press Ctrl+C to end the session; a short summary is printed.

Course rules: don't collect personal data (ask participants not to type their
name), and delete the logs when the course ends.
"""

import argparse
import json

from dotenv import load_dotenv
from openai import OpenAI

from mceca import EMOTIONS, NPC, check_llm, clean_reply, StudyLog

# ---------------------------------------------------------------- settings

CONDITIONS = {
    "expressive": {"gaze": True, "thinking": True, "gestures": True, "emotions": True},
    "neutral": {"gaze": False, "thinking": False, "gestures": False, "emotions": False},
}

BACKEND = "ollama"  # or "openai"

TASK_PROMPT = """You are Ava, a museum guide in a Minecraft village. The participant
is a visitor. Help them find out what the village is famous for (it is famous
for its giant pumpkin festival). Be friendly and patient."""

# ------------------------------------------------------------------- setup

parser = argparse.ArgumentParser(description="Run one pilot-study session.")
parser.add_argument("--participant", required=True, help="participant id, e.g. P01 (never a name)")
parser.add_argument("--condition", required=True, choices=sorted(CONDITIONS))
args = parser.parse_args()
condition = CONDITIONS[args.condition]

if BACKEND == "openai":
    load_dotenv()
    client, MODEL, EXTRA = OpenAI(), "gpt-5-nano", {"reasoning_effort": "minimal"}
else:
    client, MODEL, EXTRA = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama"), "gemma3:4b", {}
check_llm(client, MODEL)  # stops with a clear message if the LLM can't be used

log = StudyLog(participant=args.participant, condition=args.condition)
npc = NPC("Ava", skin="alex", show_status=False, log=log)  # no "connected" label for participants

SYSTEM = TASK_PROMPT + f"""
Answer ONLY with a JSON object: {{"say": "...", "emotion": "..."}}
"say": one or two short sentences, no emojis.
"emotion": one of {list(EMOTIONS) + ["none"]}."""

history = []
log.note("session started")


@npc.on_chat
def reply(player, text):
    if condition["gaze"]:
        npc.look_at(player)
    if condition["thinking"]:
        npc.thinking(True)

    history.append({"role": "user", "content": text})
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": SYSTEM}] + history[-20:],
            response_format={"type": "json_object"},
            **EXTRA,
        )
        raw = response.choices[0].message.content
        decision = json.loads(raw)
    except Exception as e:
        log.note("LLM error", error=str(e))
        npc.thinking(False)
        npc.say("Sorry, could you say that again?")
        return
    history.append({"role": "assistant", "content": raw})

    emotion = str(decision.get("emotion", "none")).lower()
    if condition["emotions"] and emotion in EMOTIONS:
        npc.emote(emotion)
    if condition["gestures"]:
        npc.gesture("nod")
    npc.say(clean_reply(decision.get("say")) or "...")


@npc.on_player_near
def approached(player):
    log.note("participant approached Ava")


print(f"Session {args.participant} / {args.condition} running. Press Ctrl+C to end it.")
try:
    npc.run()
finally:
    log.note("session ended")
    log.close()
