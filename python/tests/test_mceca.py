"""
Offline tests for the mceca library: a fake "mod" (TCP server) stands in for
Minecraft, so these run anywhere in a second:

    python -m unittest discover -s python/tests -v
"""

import csv
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import mceca
from mceca import NPC, McEcaError, StudyLog
from mceca import client as mclient


class FakeMod:
    """Accepts one connection, answers every command with ok, records requests."""

    def __init__(self):
        self.server = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen()
        self.port = self.server.getsockname()[1]
        self.requests = []
        self.conn = None
        self.results = {"take": {"item": "apple", "count": 1},
                        "surroundings": {"position": [1.0, 2.0, 3.0], "time": "12:00", "daylight": True,
                                         "weather": "clear", "biome": "plains", "players": [], "mobs": []}}
        self.errors = {}
        self.on_request = None  # optional hook: fn(msg) after each request
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        self.conn, _ = self.server.accept()
        f = self.conn.makefile("r", encoding="utf-8")
        for line in f:
            msg = json.loads(line)
            self.requests.append(msg)
            cmd = msg["cmd"]
            if cmd in self.errors:
                reply = {"re": msg["id"], "ok": False, "error": self.errors[cmd]}
            else:
                reply = {"re": msg["id"], "ok": True, "result": self.results.get(cmd, {"existing": False} if cmd == "spawn" else {})}
            self.send(reply)
            if self.on_request:
                self.on_request(msg)

    def send(self, msg):
        self.conn.sendall((json.dumps(msg) + "\n").encode())

    def last(self, cmd):
        return [r for r in self.requests if r["cmd"] == cmd][-1]


def read(path):
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


def run_briefly(seconds=0.6):
    """Run mceca.run() in the background for a moment."""
    t = threading.Thread(target=mceca.run, daemon=True)
    t.start()
    time.sleep(seconds)


class ClientTest(unittest.TestCase):
    def setUp(self):
        mclient._timers.clear()
        self.mod = FakeMod()
        self.npc = NPC("Ava", skin="alex", show_status=False, notice_range=4, port=self.mod.port)

    def test_handshake_and_spawn(self):
        hello, spawn = self.mod.requests[0], self.mod.requests[1]
        self.assertEqual(hello["cmd"], "hello")
        self.assertEqual(hello["protocol"], mclient.PROTOCOL_VERSION)
        self.assertEqual(spawn["cmd"], "spawn")
        self.assertEqual(spawn["skin"], "alex")
        self.assertFalse(spawn["show_status"])
        self.assertEqual(spawn["notice_range"], 4)

    def test_actions_send_the_right_json(self):
        self.npc.say("hi", seconds=2)
        self.assertEqual(self.mod.last("say")["text"], "hi")
        self.assertEqual(self.mod.last("say")["seconds"], 2)
        self.npc.look_at((1, 2, 3))
        self.assertEqual({k: self.mod.last("look_at")[k] for k in "xyz"}, {"x": 1, "y": 2, "z": 3})
        self.npc.look_at("Steve")
        self.assertEqual(self.mod.last("look_at")["player"], "Steve")
        self.npc.look_at(None)
        self.assertNotIn("player", self.mod.last("look_at"))
        self.npc.walk_to((5, 6, 7), speed=2)
        self.assertEqual(self.mod.last("walk_to")["speed"], 2)
        self.npc.follow("Steve", distance=2)
        self.assertEqual(self.mod.last("follow")["distance"], 2)
        self.npc.give("Steve", "bread", count=3)
        self.assertEqual(self.mod.last("give")["count"], 3)
        self.assertEqual(self.npc.take("Steve"), "apple")
        self.assertEqual(self.npc.position(), (1.0, 2.0, 3.0))
        self.assertIn("plains", self.npc.describe_surroundings())

    def test_refused_command_raises(self):
        self.mod.errors["gesture"] = "unknown gesture 'dance'"
        with self.assertRaises(McEcaError):
            self.npc.gesture("dance")

    def test_events_reach_handlers(self):
        got = []
        self.npc.on_chat(lambda p, t: got.append(("chat", p.name, t)))
        self.npc.on_click(lambda p, item: got.append(("click", p.name, item)))
        self.npc.on_player_near(lambda p: got.append(("near", p.name)))
        self.npc.on_arrive(lambda: got.append(("arrived",)))
        self.mod.send({"event": "chat", "npc": "Ava", "player": "Steve", "text": "hello", "distance": 2.0})
        self.mod.send({"event": "click", "npc": "Ava", "player": "Steve", "item": None})
        self.mod.send({"event": "player_near", "npc": "Ava", "player": "Steve", "distance": 3.0})
        self.mod.send({"event": "arrived", "npc": "Ava"})
        run_briefly()
        self.assertEqual(got, [("chat", "Steve", "hello"), ("click", "Steve", None), ("near", "Steve"), ("arrived",)])

    def test_timers(self):
        ticks, once = [], []

        @mceca.every(0.1)
        def tick():
            ticks.append(1)

        mceca.after(0.2, lambda: once.append(1))
        run_briefly(0.65)
        self.assertGreaterEqual(len(ticks), 4)
        self.assertEqual(len(once), 1)


class StudyLogTest(unittest.TestCase):
    def test_no_usernames_and_response_time(self):
        folder = tempfile.mkdtemp()
        log = StudyLog(folder=folder, condition="gaze", participant="P07")
        log._event("Ava", "chat", mceca.Player("RealUsername", 2.0), {"event": "chat", "text": "hi", "distance": 2.0})
        log._npc_action("Ava", "look_at", {"player": "RealUsername"}, {})
        log._npc_action("Ava", "say", {"text": "Hello!"}, {})
        log._event("Ava", "player_near", mceca.Player("SomeoneElse", 5.0), {"event": "player_near", "distance": 5.0})
        log.close()
        content = read(log.path)
        self.assertNotIn("RealUsername", content)
        self.assertNotIn("SomeoneElse", content)
        rows = list(csv.DictReader(content.splitlines()))
        self.assertEqual(rows[0]["participant"], "P07")
        self.assertEqual(rows[3]["participant"], "P07-other1")
        self.assertIn("response_time", json.loads(rows[2]["details"]))
        self.assertTrue(os.path.basename(log.path).endswith("_P07_gaze.csv"))


class FakeVoice:
    """Stands in for mceca.Voice: no microphone, no models."""
    can_listen = can_speak = True

    def __init__(self):
        self.listening, self.spoken = False, []

    def start_listening(self):
        self.listening = True

    def stop_listening(self):
        self.listening = False
        return "AUDIO"

    def transcribe(self, audio):
        return "come here" if audio == "AUDIO" else ""

    def synthesize(self, text):
        return ("PCM:" + text, 24000)

    def play(self, audio, rate):
        self.spoken.append((audio, rate))


class VoiceTest(unittest.TestCase):
    def setUp(self):
        mclient._timers.clear()
        self.mod = FakeMod()
        self.voice = FakeVoice()
        self.log = StudyLog(folder=tempfile.mkdtemp(), participant="P01")
        self.npc = NPC("Ava", voice=self.voice, log=self.log, port=self.mod.port)

    def tearDown(self):
        self.log.close()

    def test_push_to_talk_becomes_a_spoken_chat_message(self):
        got = []
        self.npc.on_chat(lambda p, t: got.append((p.name, t, p.spoke)))
        self.mod.send({"event": "voice_start", "npc": "Ava", "player": "Steve", "distance": 2.0})
        time.sleep(0.1)
        self.assertTrue(self.voice.listening)
        self.mod.send({"event": "voice_end", "npc": "Ava", "player": "Steve", "seconds": 1.5})
        run_briefly()
        self.assertEqual(got, [("Steve", "come here", True)])
        self.assertEqual(self.mod.last("transcript")["text"], "come here")
        rows = list(csv.DictReader(read(self.log.path).splitlines()))
        chat = [r for r in rows if r["kind"] == "chat"][0]
        self.assertTrue(json.loads(chat["details"])["voice"])

    def test_say_speaks_and_logs(self):
        self.npc.say("Hello there")
        self.assertEqual(self.mod.last("say")["text"], "Hello there")
        self.assertNotIn("spoken", self.mod.last("say"))  # logging details never go to the mod
        self.assertEqual(self.voice.spoken, [("PCM:Hello there", 24000)])
        self.npc.say("Only written", speak=False)
        self.assertEqual(len(self.voice.spoken), 1)
        rows = list(csv.DictReader(read(self.log.path).splitlines()))
        self.assertTrue(json.loads(rows[0]["details"])["spoken"])

    def test_cancelled_talk_is_ignored(self):
        got = []
        self.npc.on_chat(lambda p, t: got.append(t))
        self.mod.send({"event": "voice_start", "npc": "Ava", "player": "Steve"})
        self.mod.send({"event": "voice_end", "npc": "Ava", "player": "Steve", "cancelled": True})
        run_briefly(0.4)
        self.assertEqual(got, [])

    def test_no_voice_tells_the_player(self):
        self.npc.voice = None
        self.mod.send({"event": "voice_start", "npc": "Ava", "player": "Steve"})
        self.mod.send({"event": "voice_end", "npc": "Ava", "player": "Steve"})
        time.sleep(0.3)
        self.assertIn("voice=Voice()", self.mod.last("transcript")["error"])


class OpenAIVoiceBackendTest(unittest.TestCase):
    """What the openai backends send (no network: a fake client records the calls)."""

    def test_requests(self):
        try:
            import numpy as np
            import sounddevice  # noqa: F401  (needs the PortAudio system library on Linux)
            from mceca.voice import Voice
        except Exception:
            self.skipTest("voice extras (numpy, sounddevice) not installed")
        calls = {}

        class Fake:
            class audio:
                class transcriptions:
                    @staticmethod
                    def create(**kw):
                        calls["stt"] = kw
                        return type("R", (), {"text": " hello "})

                class speech:
                    @staticmethod
                    def create(**kw):
                        calls["tts"] = kw
                        return type("R", (), {"read": lambda self: b"\x01\x00\x02\x00"})()

        v = Voice(stt="openai", tts="openai", openai_client=Fake(), openai_voice="nova", language="en")
        self.assertEqual(v.transcribe(np.zeros(16000, dtype=np.float32) + 0.1), "hello")
        self.assertEqual(calls["stt"]["model"], "whisper-1")
        name, data, mime = calls["stt"]["file"]
        self.assertTrue(data.startswith(b"RIFF") and mime == "audio/wav")
        audio, rate = v.synthesize("Hi")
        self.assertEqual((calls["tts"]["model"], calls["tts"]["voice"], calls["tts"]["response_format"]), ("tts-1", "nova", "pcm"))
        self.assertEqual((list(audio), rate), ([1, 2], 24000))


class AgentToAgentTest(unittest.TestCase):
    def test_two_chatty_npcs_stop_after_max_npc_turns(self):
        mod_a, mod_b = FakeMod(), FakeMod()
        ava = NPC("Ava", port=mod_a.port, max_npc_turns=3)
        bob = NPC("Bob", port=mod_b.port, max_npc_turns=3)
        heard = []

        # Stand-in for the mod: whatever one NPC says, the other one hears.
        def relay(listener_mod, speaker):
            def hook(msg):
                if msg["cmd"] == "say":
                    listener_mod.send({"event": "npc_said", "npc": "?", "speaker": speaker, "text": msg["text"],
                                       "distance": 2.0, "addressed": True, "chain": msg.get("chain", 0)})
            return hook

        mod_a.on_request = relay(mod_b, "Ava")
        mod_b.on_request = relay(mod_a, "Bob")

        @ava.on_npc_say
        def ava_hears(speaker, text):          # answers everything ...
            heard.append(("Ava", speaker.name, text))
            ava.say("Ava again")

        @bob.on_npc_say
        def bob_hears(speaker, text):          # ... and so does Bob
            heard.append(("Bob", speaker.name, text))
            bob.say("Bob again")

        ava.say("Bob, hello!")                 # chain 0: started by a "player"/script
        run_briefly(1.0)
        chains = [r.get("chain", 0) for r in mod_a.requests + mod_b.requests if r["cmd"] == "say"]
        self.assertEqual(sorted(chains), [0, 1, 2, 3])   # 3 NPC-to-NPC replies, then silence
        self.assertEqual(len(heard), 3)


class RobustnessTest(unittest.TestCase):
    def setUp(self):
        mclient._timers.clear()
        self.mod = FakeMod()
        self.npc = NPC("Ava", port=self.mod.port)

    def test_a_crashing_handler_does_not_stop_the_agent(self):
        got = []

        @self.npc.on_chat
        def buggy(player, text):
            if text == "crash":
                raise KeyError("student bug")
            got.append(text)

        self.mod.send({"event": "chat", "npc": "Ava", "player": "Steve", "text": "crash"})
        self.mod.send({"event": "chat", "npc": "Ava", "player": "Steve", "text": "still alive?"})
        run_briefly()
        self.assertEqual(got, ["still alive?"])

    def test_watchdog_reports_a_stuck_handler(self):
        import contextlib, io
        mclient.STUCK_SECONDS = 0.5
        out = io.StringIO()

        @self.npc.on_chat
        def slow(player, text):
            time.sleep(3)

        self.mod.send({"event": "chat", "npc": "Ava", "player": "Steve", "text": "hi"})
        with contextlib.redirect_stdout(out):
            run_briefly(3.5)
        mclient.STUCK_SECONDS = 20.0
        self.assertIn("has been running for", out.getvalue())
        self.assertIn("time.sleep(3)", out.getvalue())


class AudioQueueTest(unittest.TestCase):
    """The output queue plays sentences one after another, resampled, without blocking."""

    def test_output_queue(self):
        try:
            import numpy as np
            from mceca import voice as v
        except ImportError:
            self.skipTest("voice extras not installed")

        class FakeSd:
            @staticmethod
            def query_devices(device, kind):
                return {"default_samplerate": 1000}

            class OutputStream:
                def __init__(self, **kw):
                    pass

                def start(self):
                    pass

        out = v._Output(np, FakeSd, None)
        out.add(np.full(10, 16384, dtype=np.int16), 1000, 1.0, 0)   # 10 samples of 0.5
        out.add(np.full(5, -16384, dtype=np.int16), 500, 1.0, 0)    # 5 samples at 500 Hz -> ~10 at 1000 Hz
        buf = np.ones((25, 1), dtype=np.float32)
        out._callback(buf, 25, None, None)
        self.assertTrue(np.allclose(buf[:10, 0], 0.5))           # first sentence ...
        self.assertTrue(np.allclose(buf[10:20, 0], -0.5))        # ... then the second one
        self.assertTrue(np.allclose(buf[20:, 0], 0.0))           # then silence
        out.add(np.full(10, 100, dtype=np.int16), 1000, 1.0, 0)
        out.clear()                                               # barge-in ...
        out.add(np.full(10, 100, dtype=np.int16), 1000, 1.0, 0)   # ... drops sentences queued before it
        out._callback(buf, 25, None, None)
        self.assertTrue(np.allclose(buf[:, 0], 0.0))
        out.add(np.full(10, 16384, dtype=np.int16), 1000, 1.0, out.generation)  # new sentences play again
        out._callback(buf, 25, None, None)
        self.assertTrue(np.allclose(buf[:10, 0], 0.5))

    def test_audio_thread_runs_jobs_in_order(self):
        try:
            from mceca import voice as v
        except ImportError:
            self.skipTest("voice extras not installed")
        t = v._AudioThread()
        order = []
        t.submit(lambda: order.append(1))
        t.submit(lambda: order.append(2))
        self.assertEqual(t.call(lambda: order.append(3) or "done"), "done")
        self.assertEqual(order, [1, 2, 3])


class CleanReplyTest(unittest.TestCase):
    def test_real_llm_leftovers_are_removed_but_normal_text_stays(self):
        cases = {
            "Bob, they've found something interesting. Let them show you, I\u2019ll wait here.\u201d} ```json {":
                "Bob, they've found something interesting. Let them show you, I\u2019ll wait here.",
            '"Hello there, traveller!"': "Hello there, traveller!",
            "Ava: *smiles warmly* Welcome to the village!": "Welcome to the village!",
            'Sure thing!"}': "Sure thing!",
            'Welcome! {"gesture": "wave"}': "Welcome!",
            "I have 3 apples [fresh ones] for you.": "I have 3 apples [fresh ones] for you.",
            "It's 5 o'clock: time for tea.": "It's 5 o'clock: time for tea.",
            'The sign says "danger" here.': 'The sign says "danger" here.',
            'Bob calls this "the old mill"': 'Bob calls this "the old mill"',
        }
        for raw, want in cases.items():
            self.assertEqual(mceca.clean_reply(raw), want)


class CheckLlmTest(unittest.TestCase):
    """check_llm() must stop with a clear message instead of failing on every chat."""

    class Client:
        def __init__(self, base_url, api_key="x", models=None):
            self.base_url, self.api_key, self._models = base_url, api_key, models

            class Models:
                def list(inner):
                    if self._models is None:
                        raise ConnectionError("refused")
                    return type("Page", (), {"data": [type("M", (), {"id": m}) for m in self._models]})

            self.models = Models()

    def test_ollama_ok(self):
        mceca.check_llm(self.Client("http://localhost:11434/v1", models=["gemma3:4b"]), "gemma3:4b")

    def test_ollama_not_running(self):
        with self.assertRaises(SystemExit):
            mceca.check_llm(self.Client("http://localhost:11434/v1", models=None), "gemma3:4b")

    def test_ollama_model_missing(self):
        with self.assertRaises(SystemExit):
            mceca.check_llm(self.Client("http://localhost:11434/v1", models=["gemma3:1b"]), "gemma3:4b")

    def test_openai_placeholder_key(self):
        with self.assertRaises(SystemExit):
            mceca.check_llm(self.Client("https://api.openai.com/v1", api_key="paste-your-key-here"), "gpt-5-nano")


class CtrlCTest(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "Windows can't send Ctrl+C to a child process this way")
    def test_ctrl_c_closes_the_log(self):
        """A script with a StudyLog stopped with Ctrl+C prints the summary."""
        mod = FakeMod()
        folder = tempfile.mkdtemp()
        script = (
            "import mceca\n"
            f"log = mceca.StudyLog(folder={folder!r}, participant='P01')\n"
            f"npc = mceca.NPC('Ava', log=log, port={mod.port})\n"
            "print('ready', flush=True)\n"
            "try:\n    npc.run()\nfinally:\n    log.note('session ended')\n"
        )
        proc = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True)
        while "ready" not in proc.stdout.readline():
            pass
        time.sleep(0.3)
        proc.send_signal(signal.SIGINT)
        out, _ = proc.communicate(timeout=10)
        self.assertIn("log saved", out)
        logfile = os.path.join(folder, os.listdir(folder)[0])
        self.assertIn("session ended", read(logfile))
        proc.stdout.close()


if __name__ == "__main__":
    unittest.main()
