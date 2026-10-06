"""
MC-ECA: Embodied Conversational Agents in Minecraft.

    from mceca import NPC

    npc = NPC("Ava")

    @npc.on_chat
    def reply(player, text):
        npc.look_at(player)
        npc.say("Hello " + player.name + "!")
        npc.gesture("nod")

    npc.run()
"""

from .client import EMOTIONS, GESTURES, NPC, McEcaError, Player, Speaker, after, clean_reply, describe, every, run
from .llmcheck import check_llm
from .studylog import StudyLog
from .voice import Voice

__all__ = ["NPC", "Player", "Speaker", "McEcaError", "StudyLog", "Voice", "check_llm", "run", "every", "after", "describe", "clean_reply", "GESTURES", "EMOTIONS"]
__version__ = "0.5.0"
