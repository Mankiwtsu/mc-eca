"""
Example 1 - your first NPC (no AI yet).

1. Start Minecraft with the MC-ECA mod and open a world.
2. Run:  python examples/01_hello.py
3. Walk up to Ava, press T and type something.

Ava turns to you, repeats what you said and nods. Every behaviour is a
function call, so you decide which ones your agent uses.
"""

from mceca import NPC

npc = NPC("Ava", skin="alex")


@npc.on_chat
def reply(player, text):
    npc.look_at(player)  # gaze: turn towards the speaker
    npc.say(f"Hi {player.name}! You said: {text}")
    npc.gesture("nod")


npc.run()
