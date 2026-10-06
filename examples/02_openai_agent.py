"""
Example 2 - an LLM agent using the course OpenAI key.

Setup (once):
    pip install -r examples/requirements.txt
    copy .env.example to .env and paste your group's key after OPENAI_API_KEY=

Run (with Minecraft open in a world):
    python examples/02_openai_agent.py

Each player gets their own conversation history, so Ava remembers what you
said earlier in the session.
"""

from dotenv import load_dotenv
from openai import OpenAI

from mceca import NPC, check_llm, clean_reply

load_dotenv()  # reads OPENAI_API_KEY from the .env file
client = OpenAI()
MODEL = "gpt-5-nano"  # the model the course key gives access to
check_llm(client, MODEL)  # stops with a clear message if the key is missing

PERSONA = """You are Ava, a friendly guide who lives in this Minecraft world.
You are curious about the player and like to help them explore.
Reply only with the words Ava says out loud: no labels, no actions in brackets, no emojis.
Keep it to one or two short sentences."""

MAX_TURNS = 10  # how many earlier question/answer pairs to send along

npc = NPC("Ava", skin="alex")
histories = {}  # player name -> list of messages


@npc.on_chat
def reply(player, text):
    npc.look_at(player)
    npc.thinking(True)  # "..." bubble while we wait for the model

    history = histories.setdefault(player.name, [])
    history.append({"role": "user", "content": text})
    messages = [{"role": "system", "content": PERSONA}] + history[-2 * MAX_TURNS:]

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            reasoning_effort="minimal",  # fastest answers; gpt-5 models "think" by default
        )
        answer = response.choices[0].message.content.strip()
    except Exception as e:  # no internet, wrong key, ...
        print("LLM error:", e, "(see docs/04-troubleshooting.md)")
        npc.thinking(False)
        npc.say("Sorry, I lost my train of thought.")
        return

    history.append({"role": "assistant", "content": answer})
    npc.say(clean_reply(answer))


npc.run()
