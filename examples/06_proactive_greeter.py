"""
Example 6 - a proactive agent: it notices you, greets you, and idles.

No AI needed. This shows the *non-verbal* side of an embodied agent:
  * when you come close, Ava turns to you, waves and greets you
  * when you walk away, she says goodbye and stops looking at you
  * while nobody is around, she glances around now and then (idle behaviour)
  * right-click her with an item to hand it over; punch her and she gets angry

Run (with Minecraft open in a world):
    python examples/06_proactive_greeter.py
Then walk away from Ava (more than 7 blocks) and come back.
"""

import random

import mceca
from mceca import NPC

npc = NPC("Ava", skin="alex", notice_range=6)  # "near" = within 6 blocks
visitors = set()  # players currently close to Ava


@npc.on_player_near
def greet(player):
    visitors.add(player.name)
    npc.look_at(player)
    npc.gesture("wave")
    npc.emote("happy")
    npc.say(f"Hello {player.name}! Welcome to my little corner of the world.")


@npc.on_player_leave
def goodbye(player):
    visitors.discard(player.name)
    npc.say("Goodbye, come back soon!")
    npc.look_at(None)


@npc.on_chat
def reply(player, text):
    npc.look_at(player)
    npc.gesture("nod")
    npc.say("I'm just a greeter. Try example 7 for a real conversation!")


@npc.on_click
def clicked(player, item):
    npc.look_at(player)
    if item is None:
        npc.say("Hi! Bring me something and right-click me with it.")
        return
    npc.take(player)  # Ava now holds the item
    npc.emote("love")
    npc.say(f"A {item.replace('_', ' ')}, for me? Thank you!")


@npc.on_hit
def hit(player):
    npc.emote("angry")
    npc.gesture("shake")
    npc.say("Hey! That hurt.")


@mceca.every(6)
def idle():
    """Idle gaze: while nobody is near, look at a random spot every 6 seconds."""
    if visitors:
        return
    pos = npc.position()
    if pos:
        x, y, z = pos
        npc.look_at((x + random.uniform(-6, 6), y + random.uniform(0.5, 2.5), z + random.uniform(-6, 6)))


npc.run()
