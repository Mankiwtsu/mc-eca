"""
Example 3 - the same agent with a free, local model (Ollama).

Nothing leaves your laptop and no API key is needed, but answers are slower
on older laptops.

Setup (once):
    1. Install Ollama from https://ollama.com
    2. ollama pull gemma3:4b         (about 3 GB; on weak laptops try gemma3:1b)
    3. pip install -r examples/requirements.txt

Run (with Minecraft open in a world):
    python examples/03_ollama_agent.py

The code is identical to example 2 except for the client and the model:
Ollama speaks the same API as OpenAI.
"""

from openai import OpenAI

from mceca import NPC, check_llm, clean_reply

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")  # key is ignored
MODEL = "gemma3:4b"
check_llm(client, MODEL)  # stops with a clear message if Ollama isn't running

PERSONA = """You are Ava, a friendly guide who lives in this Minecraft world.
You are curious about the player and like to help them explore.
Reply only with the words Ava says out loud: no labels, no actions in brackets, no emojis.
Keep it to one or two short sentences."""

MAX_TURNS = 10

npc = NPC("Ava", skin="alex")
histories = {}


@npc.on_chat
def reply(player, text):
    npc.look_at(player)
    npc.thinking(True)

    history = histories.setdefault(player.name, [])
    history.append({"role": "user", "content": text})
    messages = [{"role": "system", "content": PERSONA}] + history[-2 * MAX_TURNS:]

    try:
        response = client.chat.completions.create(model=MODEL, messages=messages)
        answer = response.choices[0].message.content.strip()
    except Exception as e:  # Ollama not running, model not pulled, ...
        print("LLM error:", e, "(see docs/04-troubleshooting.md)")
        npc.thinking(False)
        npc.say("Sorry, I lost my train of thought.")
        return

    history.append({"role": "assistant", "content": answer})
    npc.say(clean_reply(answer))


npc.run()
