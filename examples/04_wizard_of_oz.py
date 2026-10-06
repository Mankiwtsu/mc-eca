"""
Example 4 - Wizard of Oz: a human types the NPC's answers.

Useful for pilot studies: test an interaction design before the AI is ready,
or compare the AI against a human. The participant plays in Minecraft; the
experimenter ("wizard") reads the messages in this terminal and answers.

Run (with Minecraft open in a world):
    python examples/04_wizard_of_oz.py

What you can type when a message comes in:
    Sure, follow me!          -> Ava says this
    /nod                      -> Ava nods (any gesture: nod, shake, wave, crouch, jump)
    /nod Sure, follow me!     -> both
    (empty line)              -> Ava says nothing
"""

from mceca import NPC

npc = NPC("Ava", skin="alex")


@npc.on_chat
def reply(player, text):
    npc.look_at(player)
    npc.thinking(True)

    print(f"\n{player.name}: {text}")
    answer = input("Ava> ").strip()

    if answer.startswith("/"):
        gesture, _, answer = answer[1:].partition(" ")
        npc.gesture(gesture)
    if answer:
        npc.say(answer)
    else:
        npc.thinking(False)


print("Wizard of Oz mode: answer as Ava when players talk to her.")
npc.run()
