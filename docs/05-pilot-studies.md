# 05 – Pilot studies

How to run a small pilot study with MC-ECA: setting up conditions, running sessions,
the log format, and a first analysis. Start from
[`examples/08_pilot_study.py`](../examples/08_pilot_study.py).

## 1. Decide what you compare

A pilot in this course evaluates **user perception, usability and interaction design**
of one embodiment with verbal dialogue plus **one additional modality**. In MC-ECA, that
modality can be:

| Modality | Calls | Example condition |
|----------|-------|-------------------|
| Gaze | `look_at` | looks at the participant vs. looks around |
| Gestures | `gesture` | LLM-chosen gestures vs. none |
| Emotion display | `emote` | emotions vs. none |
| Turn-taking cues | `thinking` | "..." bubble while generating vs. none |
| Proxemics / movement | `walk_to`, `follow` | approaches the participant vs. waits; follow distance 2 vs. 5 |
| Objects | `hold`, `give`, `take` | hands over items vs. only talks about them |
| Multi-party | `on_npc_say`, `look_at(speaker)` | one agent vs. two agents; listeners look at the speaker vs. not |
| Voice | `Voice`, `say(..., speak=)` | spoken vs. written answers; voice vs. typed input (see [06 – Voice](06-voice.md)) |

Keep the **words the same** across conditions where you can (same persona, same model)
and change only the modality you study.

## 2. Put the conditions in the script

The template keeps all switches in one place:

```python
CONDITIONS = {
    "expressive": {"gaze": True,  "thinking": True,  "gestures": True,  "emotions": True},
    "neutral":    {"gaze": False, "thinking": False, "gestures": False, "emotions": False},
}
...
if condition["gaze"]:
    npc.look_at(player)
```

and takes the condition and participant id from the command line:

```bash
python examples/08_pilot_study.py --participant P01 --condition expressive
```

```bash
python examples/08_pilot_study.py --participant P02 --condition neutral
```

Use **participant ids**, never names. Keep the list that links ids to people (if you
need one at all) on paper or in a separate protected file, not in the logs.

## 3. Prepare the world and the session

* Build the setting (a room, a village, a task area) in a world **once**, then copy the
  world folder (`.minecraft/saves/<world>`) so every participant starts from the same
  state.
* Hide the developer labels: `NPC("Ava", show_status=False)` (and `show_name=False` if
  the name shouldn't be visible).
* Turn off *Pause on lost focus* (**F3 + P**).
* Put the NPC where it should stand: start the script once, walk to the place you want,
  `/eca remove Ava`, restart the script there. The NPC is saved with the world.
* Do a full test session yourself first.

## 4. During a session

1. Open the world copy and start the script with the participant id and condition.
2. Give the participant the task and the informed consent form (see the course page
   *Working with participants*).
3. Add notes for things you observe:
   ```python
   log.note("participant asked for help with the controls")
   ```
   (or add a timer/key in your script that writes notes).
4. End the session with **Ctrl+C**. The log closes and prints a summary:
   ```
   [mceca] log saved: logs/2026-10-05_14-03-22_P01_expressive.csv (12 player messages, 12 NPC utterances, mean response time 1.84 s)
   ```

## 5. The log file

`logs/<date>_<time>_<participant>_<condition>.csv`, one row per event or action:

| time | seconds | participant | condition | npc | actor | kind | text | details |
|------|---------|-------------|-----------|-----|-------|------|------|---------|
| 2026-10-05T22:33:58.288 | 15.339 | P01 | expressive | Ava | player | player_near | | {"distance": 3.0} |
| 2026-10-05T22:34:03.294 | 20.345 | P01 | expressive | Ava | player | chat | Hello! I just arrived in this village. | {"distance": 3.0} |
| 2026-10-05T22:34:03.295 | 20.346 | P01 | expressive | Ava | npc | look_at | | {"player": "P01"} |
| 2026-10-05T22:34:03.338 | 20.389 | P01 | expressive | Ava | npc | thinking | | {"on": true} |
| 2026-10-05T22:34:06.641 | 23.692 | P01 | expressive | Ava | npc | emote | | {"name": "happy"} |
| 2026-10-05T22:34:06.690 | 23.741 | P01 | expressive | Ava | npc | gesture | | {"name": "nod"} |
| 2026-10-05T22:34:06.741 | 23.792 | P01 | expressive | Ava | npc | say | Welcome, welcome! It's lovely to have you visit our village. | {"response_time": 3.447} |

(A real log from testing the template with a local model.)

`response_time` is the time from the participant's message to the NPC's answer
(including the LLM). It's useful when you study turn-taking or perceived
responsiveness.

## 6. A first analysis (pandas)

```python
import glob, json
import pandas as pd

df = pd.concat(pd.read_csv(f, encoding="utf-8-sig") for f in glob.glob("logs/*.csv"))
df["details"] = df["details"].fillna("{}").map(json.loads)

says = df[(df.actor == "npc") & (df.kind == "say")].copy()
says["response_time"] = says["details"].map(lambda d: d.get("response_time"))

print(says.groupby("condition")["response_time"].describe())        # latency per condition
print(df[df.actor == "player"].groupby(["condition", "participant"]).size())   # messages per participant
print(df[df.kind == "gesture"]["details"].map(lambda d: d["name"]).value_counts())  # which gestures
```

For a pilot, combine these numbers with **qualitative data**: what participants said
during the session (the `chat` rows), your notes, and a short interview or questionnaire
afterwards (e.g. Godspeed, SUS, or your own questions).

## 7. Course rules: data

* No personal data in logs. MC-ECA never writes usernames, but what participants **type**
  is logged as-is, so ask them not to type their name or other personal details.
* Store logs on your own laptop or the university's storage, not in public places
  (`logs/` is excluded from git).
* **Delete the logs when the course ends.**
* Using the OpenAI examples sends what participants type to OpenAI; the Ollama examples
  keep everything on the laptop. Mention this in your consent form.
