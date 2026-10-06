"""
Example 9 - talk to the NPC with your voice, and hear it answer.

In Minecraft, walk up to Ava, HOLD V while you speak, and let go. What you said
appears in the chat as "[voice] ...", and Ava answers out loud (and in her bubble).

Setup (once):
    pip install -e "python[voice]"        # speech packages (a few hundred MB)
    + the LLM setup of example 3 (Ollama) or example 2 (course key)

The first start downloads the speech models (~150 MB for Whisper, ~60 MB for the
voice). On macOS, allow your terminal / editor to use the microphone when asked.

Run (with Minecraft open in a world):
    python examples/09_voice_agent.py

Everything runs on your laptop with BACKEND = "ollama" and VOICE = "local".
With the course key, use "openai" for both (OpenAI whisper-1 and tts-1).
"""

from dotenv import load_dotenv
from openai import OpenAI

from mceca import NPC, check_llm, clean_reply, Voice

BACKEND = "ollama"  # LLM: "ollama" or "openai"
VOICE = "local"     # speech: "local" (faster-whisper + Piper) or "openai" (whisper-1 + tts-1)

load_dotenv()
if BACKEND == "openai":
    client, MODEL, EXTRA = OpenAI(), "gpt-5-nano", {"reasoning_effort": "minimal"}
else:
    client, MODEL, EXTRA = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama"), "gemma3:4b", {}
check_llm(client, MODEL)

if VOICE == "openai":
    voice = Voice(stt="openai", tts="openai", openai_voice="nova")
else:
    voice = Voice(stt="local", tts="local", piper_voice="en_US-lessac-medium")

PERSONA = """You are Ava, a friendly guide who lives in this Minecraft world.
The player talks to you with their voice and you answer out loud.
Reply only with the words Ava says: one or two short, natural spoken sentences,
no lists, no emojis, no actions in brackets."""

npc = NPC("Ava", skin="alex", voice=voice)
histories = {}


@npc.on_player_near
def greet(player):
    npc.look_at(player)
    npc.gesture("wave")
    npc.say("Hi there! Hold V and talk to me.")


@npc.on_chat  # typed AND spoken messages arrive here
def reply(player, text):
    print(f"{player.name} ({'spoke' if player.spoke else 'typed'}): {text}")
    npc.look_at(player)
    npc.thinking(True)

    history = histories.setdefault(player.name, [])
    history.append({"role": "user", "content": text})
    try:
        response = client.chat.completions.create(
            model=MODEL, messages=[{"role": "system", "content": PERSONA}] + history[-20:], **EXTRA)
        answer = response.choices[0].message.content.strip()
    except Exception as e:
        print("LLM error:", e, "(see docs/04-troubleshooting.md)")
        npc.thinking(False)
        npc.say("Sorry, I lost my train of thought.")
        return
    history.append({"role": "assistant", "content": answer})

    npc.say(clean_reply(answer))  # bubble + spoken out loud
    npc.gesture("nod")


npc.run()
