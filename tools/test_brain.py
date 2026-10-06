"""
Scripted brain for the automated in-game test (maintainers only).

Reacts to keywords in chat so every feature can be checked with screenshots:
    nod / shake / wave / crouch / jump              -> that gesture
    happy / love / angry / sad / surprised / confused -> that emotion
    think                                           -> thinking bubble for 3 s, then an answer
    come                                            -> walk_to(player)
    follow / stop                                   -> follow(player) / stop()
    east                                            -> walk 6 blocks east (a position)
    look there                                      -> look at a point 5 blocks east
    hold                                            -> hold a diamond
    give                                            -> give the held item to the player
    where                                           -> say describe_surroundings()
    anything else                                   -> echo
and to events: player near/leave, right-click (takes the item you hold), punch,
arrived, stuck. Writes a StudyLog to logs/ in the current folder.

Used together with:  cd mod && ./gradlew runClientGameTest
(see docs/maintainers/building-the-mod.md)
"""

import time

from mceca import NPC, StudyLog

log = StudyLog(folder="logs", condition="test", participant="T01")
npc = NPC("Ava", skin="alex", log=log)

GESTURES = ("nod", "shake", "wave", "crouch", "jump")
EMOTIONS = ("happy", "love", "angry", "sad", "surprised", "confused")


@npc.on_chat
def reply(player, text):
    lower = text.lower()
    npc.look_at(player)
    for gesture in GESTURES:
        if gesture in lower:
            npc.gesture(gesture)
            npc.say(f"Here is a {gesture}!")
            return
    for emotion in EMOTIONS:
        if emotion in lower:
            npc.emote(emotion)
            npc.say(f"I feel {emotion}!")
            return
    if "think" in lower:
        npc.thinking(True)
        time.sleep(3)
        npc.say("Hmm... I thought about it. The answer is 42.")
    elif "come" in lower:
        npc.say("On my way!")
        npc.walk_to(player)
    elif "follow" in lower:
        npc.say("I'll follow you.")
        npc.follow(player, distance=3)
    elif "stop" in lower:
        npc.stop()
        npc.say("Okay, I'll wait here.")
    elif "east" in lower:
        x, y, z = npc.position()
        npc.say("Walking east!")
        npc.walk_to((x + 6, y, z))
    elif "look there" in lower:
        x, y, z = npc.position()
        npc.look_at((x + 5, y + 1.5, z))
        npc.say("What is over there?")
    elif "hold" in lower:
        npc.hold("diamond")
        npc.say("Look, a diamond!")
    elif "give" in lower:
        npc.give(player)
        npc.say("Here, take it.")
    elif "where" in lower:
        npc.say(npc.describe_surroundings())
    else:
        npc.say(f"You said: {text}")


@npc.on_player_near
def noticed(player):
    npc.look_at(player)
    npc.gesture("wave")
    npc.say("Oh, hello there!")


@npc.on_player_leave
def left(player):
    npc.say("Bye!")


@npc.on_click
def clicked(player, item):
    npc.look_at(player)
    if item:
        taken = npc.take(player)
        npc.emote("happy")
        npc.say(f"For me? A {taken.replace('_', ' ')}! Thank you!")
    else:
        npc.say("You poked me!")


@npc.on_hit
def hit(player):
    npc.emote("angry")
    npc.gesture("shake")
    npc.say("Ouch! Don't hit me.")


@npc.on_arrive
def arrived():
    npc.say("I'm here!")


@npc.on_stuck
def stuck():
    npc.emote("confused")
    npc.say("I can't get there.")


npc.run()
