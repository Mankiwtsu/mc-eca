"""Maintainer test: two NPCs in one script must spawn side by side and answer separately."""

import mceca
from mceca import NPC

ava = NPC("Ava", skin="alex")
bob = NPC("Bob", skin="Notch", show_status=False)  # username skin (needs internet)


@ava.on_chat
def ava_reply(player, text):
    ava.look_at(player)
    ava.say("I'm Ava. Ask Bob too!")


@bob.on_chat
def bob_reply(player, text):
    bob.look_at(player)
    bob.say("Bob here, hello!")
    bob.gesture("wave")


mceca.run()
