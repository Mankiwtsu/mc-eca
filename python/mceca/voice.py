"""
Voice for NPCs: speech-to-text for push-to-talk, and text-to-speech for say().

    from mceca import NPC, Voice

    npc = NPC("Ava", voice=Voice())                          # free & offline
    npc = NPC("Ava", voice=Voice(stt="openai", tts="openai"))  # course OpenAI key

In Minecraft, hold V near the NPC while you speak. What you said arrives in your
normal @npc.on_chat handler (player.spoke is True), and npc.say() speaks out loud.

Backends:
  stt="local"   faster-whisper (Whisper running on your laptop, ~150 MB download once)
  stt="openai"  OpenAI whisper-1 (needs OPENAI_API_KEY)
  tts="local"   Piper (neural voice running on your laptop, ~60 MB download once)
  tts="openai"  OpenAI tts-1 (needs OPENAI_API_KEY)
  None          turn that half off (e.g. tts=None: the NPC listens but only writes)

Install the extra packages once:   pip install -e "python[voice]"
"""

from __future__ import annotations

import io
import os
import threading
import time
import wave
from pathlib import Path
from typing import Optional, Tuple

SAMPLE_RATE = 16000  # Whisper works with 16 kHz mono
MIN_SECONDS = 0.3
MAX_SECONDS = 30.0
CACHE_DIR = Path(os.environ.get("MCECA_CACHE", Path.home() / ".cache" / "mceca"))


def _log(msg: str) -> None:
    print(f"[mceca] {msg}", flush=True)


def _need(module: str):
    try:
        return __import__(module)
    except ImportError:
        raise SystemExit(
            f"[mceca] Voice needs the package '{module}'. Install the voice extras once with:\n"
            f'  pip install -e "python[voice]"'
        ) from None


# --------------------------------------------------------------- audio thread
#
# Every call into the sound system (opening the microphone, playing, stopping) runs on
# ONE background thread. Sound drivers (CoreAudio on macOS especially) can block when
# they are used from several threads at once, e.g. the player pressing V while the NPC
# starts to speak. On this thread a hang can only delay audio, never the connection to
# Minecraft or your agent code.

class _AudioThread:
    def __init__(self):
        import queue as _queue
        self._jobs = _queue.Queue()
        threading.Thread(target=self._loop, name="mceca-audio", daemon=True).start()

    def _loop(self):
        while True:
            fn, done = self._jobs.get()
            try:
                result = fn()
            except Exception as e:
                _log(f"audio error: {e}")
                result = None
            if done is not None:
                done.append(result)
                done.append(None)  # marker: finished

    def submit(self, fn) -> None:
        """Run fn on the audio thread, don't wait."""
        self._jobs.put((fn, None))

    def call(self, fn, timeout: float = 10.0):
        """Run fn on the audio thread and wait for its result (None after `timeout`)."""
        done = []
        self._jobs.put((fn, done))
        deadline = time.monotonic() + timeout
        while len(done) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        if len(done) < 2:
            _log("the audio device is not responding (try another microphone/speaker, or restart the script)")
            return None
        return done[0]


class _Output:
    """One continuously open output stream; play() just appends samples to a queue,
    so sentences play one after another and nothing ever waits for the sound card."""

    def __init__(self, np, sd, device):
        self.np, self.sd, self.device = np, sd, device
        self.rate = None
        self.stream = None
        self.buffer = []  # float32 chunks waiting to be played
        self.lock = threading.Lock()
        self.generation = 0  # bumped by clear(): sentences queued before that are dropped

    def _ensure(self):  # audio thread only
        if self.stream is None:
            info = self.sd.query_devices(self.device, "output")
            self.rate = int(info["default_samplerate"])
            self.stream = self.sd.OutputStream(samplerate=self.rate, channels=1, dtype="float32",
                                               device=self.device, callback=self._callback)
            self.stream.start()

    def _callback(self, outdata, frames, time_info, status):
        out = outdata[:, 0]
        filled = 0
        with self.lock:
            while filled < frames and self.buffer:
                chunk = self.buffer[0]
                n = min(frames - filled, len(chunk))
                out[filled:filled + n] = chunk[:n]
                filled += n
                if n < len(chunk):
                    self.buffer[0] = chunk[n:]
                else:
                    self.buffer.pop(0)
        out[filled:] = 0

    def add(self, audio_int16, rate, volume, generation):  # audio thread only
        if generation != self.generation:
            return  # the player interrupted after this sentence was queued
        self._ensure()
        np = self.np
        audio = audio_int16.astype(np.float32) / 32768.0 * volume
        if rate != self.rate and len(audio) > 1:
            n = int(len(audio) * self.rate / rate)
            audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)
        with self.lock:
            if generation == self.generation:
                self.buffer.append(np.clip(audio, -1.0, 1.0))

    def clear(self):
        with self.lock:
            self.generation += 1
            self.buffer.clear()


_audio = None            # the shared _AudioThread
_outputs = {}            # output device -> _Output (shared by all NPCs)
_whisper_models = {}     # model name -> loaded faster-whisper model (shared by all Voices)
_piper_voices = {}       # voice name -> loaded Piper voice


def _audio_thread() -> _AudioThread:
    global _audio
    if _audio is None:
        _audio = _AudioThread()
    return _audio


class Voice:
    """Speech in and out for an NPC. Pass it to NPC(..., voice=Voice(...)).

    stt / tts:      "local", "openai" or None (see the module docstring)
    language:       spoken language for speech-to-text, e.g. "en", "nl"; None = detect
    whisper_model:  local Whisper size: "tiny", "base" (default), "small" (better, slower)
    piper_voice:    local voice, e.g. "en_US-lessac-medium", "en_GB-alba-medium",
                    "nl_NL-mls-medium" (list: https://huggingface.co/rhasspy/piper-voices)
    openai_voice:   tts-1 voice: alloy, echo, fable, onyx, nova, shimmer
    openai_client:  an openai.OpenAI() client (default: one is created from OPENAI_API_KEY)
    interruptible:  stop the NPC's speech when the player starts talking (barge-in)
    volume:         0.0 - 1.0 (or more) for the NPC's voice
    input_device / output_device: sounddevice device number or name (default: system default)
    """

    def __init__(
        self,
        stt: Optional[str] = "local",
        tts: Optional[str] = "local",
        language: Optional[str] = "en",
        whisper_model: str = "base",
        piper_voice: str = "en_US-lessac-medium",
        openai_voice: str = "alloy",
        openai_client=None,
        interruptible: bool = True,
        volume: float = 1.0,
        input_device=None,
        output_device=None,
    ):
        self.np = _need("numpy")
        self.sd = _need("sounddevice")
        self.language = language
        self.interruptible = interruptible
        self.volume = volume
        self.input_device = input_device
        self.output_device = output_device
        self._openai = openai_client

        self._stt = self._make_stt(stt, whisper_model)
        self._tts = self._make_tts(tts, piper_voice, openai_voice)
        self._stream = None
        self._chunks = []
        self._lock = threading.Lock()

    @property
    def can_listen(self) -> bool:
        return self._stt is not None

    @property
    def can_speak(self) -> bool:
        return self._tts is not None

    # ----------------------------------------------------------- listening

    def start_listening(self) -> None:
        """Start recording the microphone (the player pressed the talk key).
        Returns at once; the microphone is opened on the audio thread."""
        if self.interruptible:
            self.stop_speaking()
        with self._lock:
            self._chunks = []
        if os.environ.get("MCECA_FAKE_MIC"):
            return  # tests: the audio comes from a file, see stop_listening()

        def open_mic():
            def callback(indata, frames, time_info, status):
                self._chunks.append(indata[:, 0].copy())

            try:
                stream = self.sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                             device=self.input_device, callback=callback)
                stream.start()
                self._stream = stream
            except Exception as e:  # no microphone, no permission, ...
                self._stream = None
                _log(f"can't open the microphone: {e}")

        _audio_thread().submit(open_mic)

    def stop_listening(self):
        """Stop recording and return the audio (float32 numpy array, 16 kHz), or None
        if there was nothing usable. Waits for the audio thread (max 10 s), so don't
        call it from the connection thread."""
        fake = os.environ.get("MCECA_FAKE_MIC")
        if fake:
            audio = _read_wav(fake, self.np)
        else:
            def close_mic():
                stream, self._stream = self._stream, None
                if stream is not None:
                    stream.stop()
                    stream.close()
                with self._lock:
                    return self.np.concatenate(self._chunks) if self._chunks else None

            audio = _audio_thread().call(close_mic)
            if audio is None:
                return None
        seconds = len(audio) / SAMPLE_RATE
        if seconds < MIN_SECONDS:
            return None
        audio = audio[: int(MAX_SECONDS * SAMPLE_RATE)]
        if float(self.np.max(self.np.abs(audio))) < 1e-4:
            _log("the microphone only recorded silence. On macOS: System Settings -> Privacy & "
                 "Security -> Microphone -> allow your terminal / editor, then restart it.")
            return None
        return audio

    def transcribe(self, audio) -> str:
        """Speech -> text."""
        return self._stt(audio).strip() if self._stt else ""

    # ------------------------------------------------------------ speaking

    def synthesize(self, text: str):
        """Text -> (int16 numpy array, sample rate)."""
        return self._tts(text)

    def play(self, audio, rate: int) -> None:
        """Queue audio to be played; returns at once. Sentences play one after another
        (also between NPCs), and a player starting to talk clears the queue."""
        out_dir = os.environ.get("MCECA_TTS_OUT")
        if out_dir:  # tests: keep what was said
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            _write_wav(Path(out_dir) / f"say-{time.time():.3f}.wav", audio, rate)
        if os.environ.get("MCECA_MUTE"):
            return
        output = self._output()
        generation = output.generation
        _audio_thread().submit(lambda: output.add(audio, rate, self.volume, generation))

    def stop_speaking(self) -> None:
        """Stop the NPC's speech (also what is still waiting in the queue)."""
        out = _outputs.get(self.output_device)
        if out is not None:
            out.clear()

    def _output(self) -> _Output:
        if self.output_device not in _outputs:
            _outputs[self.output_device] = _Output(self.np, self.sd, self.output_device)
        return _outputs[self.output_device]

    # ------------------------------------------------------------ backends

    def _client(self):
        if self._openai is None:
            openai = _need("openai")
            self._openai = openai.OpenAI()
        return self._openai

    def _make_stt(self, kind, whisper_model):
        if kind is None:
            return None
        if kind == "openai":
            def stt(audio):
                buf = io.BytesIO()
                _write_wav(buf, (self.np.clip(audio, -1, 1) * 32767).astype(self.np.int16), SAMPLE_RATE)
                result = self._client().audio.transcriptions.create(
                    model="whisper-1", file=("speech.wav", buf.getvalue(), "audio/wav"),
                    **({"language": self.language} if self.language else {}))
                return result.text
            return stt
        if kind == "local":
            fw = _need("faster_whisper")
            if whisper_model not in _whisper_models:  # one copy, even with several NPCs
                _log(f"loading speech recognition (Whisper '{whisper_model}'; the first time this downloads it) ...")
                _whisper_models[whisper_model] = fw.WhisperModel(whisper_model, device="cpu", compute_type="int8")
            model = _whisper_models[whisper_model]

            def stt(audio):
                segments, _ = model.transcribe(audio, language=self.language, beam_size=1, vad_filter=True)
                return " ".join(s.text.strip() for s in segments)
            return stt
        raise ValueError(f"stt must be 'local', 'openai' or None, not {kind!r}")

    def _make_tts(self, kind, piper_voice, openai_voice):
        if kind is None:
            return None
        if kind == "openai":
            def tts(text):
                response = self._client().audio.speech.create(
                    model="tts-1", voice=openai_voice, input=text, response_format="pcm")
                data = response.read() if hasattr(response, "read") else response.content
                return self.np.frombuffer(data, dtype=self.np.int16), 24000  # tts-1 pcm = 24 kHz 16-bit mono
            return tts
        if kind == "local":
            _need("piper")
            from piper import PiperVoice
            folder = CACHE_DIR / "piper"
            model_path = folder / f"{piper_voice}.onnx"
            if not model_path.exists():
                from piper.download_voices import download_voice
                _log(f"downloading the voice '{piper_voice}' (once, ~60 MB) ...")
                folder.mkdir(parents=True, exist_ok=True)
                download_voice(piper_voice, folder)
            if piper_voice not in _piper_voices:
                _piper_voices[piper_voice] = PiperVoice.load(str(model_path))
            voice = _piper_voices[piper_voice]
            rate = voice.config.sample_rate

            def tts(text):
                chunks = [c.audio_int16_array for c in voice.synthesize(text)]
                return (self.np.concatenate(chunks) if chunks else self.np.zeros(0, dtype=self.np.int16)), rate
            return tts
        raise ValueError(f"tts must be 'local', 'openai' or None, not {kind!r}")


def _write_wav(target, audio, rate: int) -> None:
    with wave.open(target if not isinstance(target, Path) else str(target), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(audio.tobytes())


def _read_wav(path: str, np):
    """Read a 16-bit wav file as float32 at 16 kHz (for tests with MCECA_FAKE_MIC)."""
    with wave.open(path) as w:
        rate = w.getframerate()
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        if w.getnchannels() > 1:
            audio = audio.reshape(-1, w.getnchannels()).mean(axis=1)
    if rate != SAMPLE_RATE:
        n = int(len(audio) * SAMPLE_RATE / rate)
        audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)
    return audio
