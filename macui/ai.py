"""The assistant.

macOS talks to Siri, to the Writing Tools and to Visual Intelligence.
Here the same three things talk to a local ollama server, so nothing ever
leaves the machine:

* ``ask``    a free question, the way Spotlight asks Siri,
* ``write``  rewrite, proofread, summarise or change the tone of a text,
* ``screen`` describe what is on the display.

The server is optional: when ollama is not running the panels say so
instead of failing.
"""

from __future__ import annotations

import base64
import json
import signal
import os
import shutil
import subprocess
import urllib.error
import urllib.request

OLLAMA_URL = os.environ.get("MACSHELL_OLLAMA", "http://localhost:11434")

WRITE_SYSTEM = (
    "You are the Writing Tools of macOS.  You rewrite, proofread, summarise "
    "or change the tone of the text the user gives you.  Answer with the "
    "text itself, without a preamble and without quotes."
)

SCREEN_SYSTEM = (
    "You are the Visual Intelligence of macOS.  Describe what is on the "
    "screen in a few clear sentences: the applications, what they show and "
    "anything that looks important."
)

ASK_SYSTEM = (
    "You are Siri on macOS.  Answer the question in a few clear sentences. "
    "Say it is a local model when you are asked about yourself."
)

MODELS = {
    "ask": ("llama3.2", "qwen2.5", "gemma3"),
    "write": ("llama3.2", "qwen2.5", "gemma3"),
    "screen": ("llava", "llama3.2-vision", "moondream"),
}


def installed():
    """True when the ollama binary is on the machine."""
    return shutil.which("ollama") is not None


def models():
    """The models the local server offers."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2) as fh:
            data = json.load(fh)
    except Exception:  # noqa: BLE001
        return []
    names = []
    for entry in data.get("models", []):
        name = entry.get("name") or entry.get("model") or ""
        if name:
            names.append(name)
    return names


def running():
    """True when the server answers."""
    return bool(models())


def _pick(kind):
    """Choose a model for the job, preferring the ones that fit."""
    available = models()
    if not available:
        return None
    for wanted in MODELS.get(kind, ()):
        for name in available:
            if name.split(":")[0] == wanted:
                return name
    return available[0]


def _post(payload, timeout=120):
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as fh:
        return json.load(fh)


def chat(kind, prompt, system=None, images=None):
    """Ask the local model.  Returns (answer, error)."""
    if not installed():
        return None, ("ollama is not installed on this machine.  "
                      "Install it and run: ollama pull llama3.2")
    model = _pick(kind)
    if model is None:
        return None, ("No model found.  Pull one with: ollama pull llama3.2 "
                      "(and ollama pull llava for the screen)")
    if system is None:
        system = {"write": WRITE_SYSTEM, "screen": SCREEN_SYSTEM,
                  "ask": ASK_SYSTEM}.get(kind, "")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    message = {"role": "user", "content": prompt}
    if images:
        message["images"] = images
    messages.append(message)
    try:
        data = _post({"model": model, "messages": messages, "stream": False})
    except urllib.error.URLError:
        return None, ("The ollama server is not answering.  Start it with: "
                      "ollama serve")
    except Exception as exc:  # noqa: BLE001
        return None, f"The model failed: {exc}"
    answer = (data.get("message") or {}).get("content", "")
    return answer.strip(), None


def screenshot():
    """A picture of the screen, as the model wants it."""
    path = "/tmp/macshell-screen.png"
    try:
        subprocess.run(["grim", path], check=True, capture_output=True,
                       timeout=10)
    except Exception:  # noqa: BLE001
        return None
    try:
        with open(path, "rb") as fh:
            return base64.b64encode(fh.read()).decode()
    except OSError:
        return None


def write_actions(text):
    """The four writing tools, as macOS offers them."""
    return [
        ("Rewrite", "Rewrite this text so it reads better, keeping the "
                    "meaning and the language."),
        ("Proofread", "Proofread this text and correct the spelling, the "
                      "grammar and the punctuation."),
        ("Summarise", "Summarise this text in three sentences."),
        ("Make it formal", "Rewrite this text in a formal, professional "
                            "tone."),
        ("Make it friendly", "Rewrite this text in a friendly, casual "
                             "tone."),
        ("Make it shorter", "Rewrite this text in half the words."),
    ]


def apply_action(action, text):
    """Run one writing tool over the text."""
    prompt = f"{action}\n\n{text}"
    return chat("write", prompt, system=WRITE_SYSTEM)


# --- voice ------------------------------------------------------------------
#
# macOS listens to you.  Here the microphone is recorded with pipewire and
# the words are written by whatever speech recognition is on the machine:
# whisper.cpp, the openai-whisper command or vosk.

VOICE_FILE = "/tmp/macshell-voice.wav"
WHISPER_MODEL = os.environ.get(
    "MACSHELL_WHISPER_MODEL",
    os.path.expanduser("~/.cache/macshell/ggml-base.bin"))

_recorder = None


def start_recording():
    """Start recording from the default microphone."""
    global _recorder
    stop_recording()
    command = ["pw-record", "--rate", "16000", "--channels", "1",
               "--format", "s16", VOICE_FILE]
    try:
        _recorder = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
    except OSError:
        _recorder = None
    return _recorder is not None


def stop_recording():
    """Stop the recording and return the file that was written."""
    global _recorder
    if _recorder is None:
        return None
    try:
        _recorder.send_signal(signal.SIGINT)
        _recorder.wait(timeout=5)
    except Exception:  # noqa: BLE001
        try:
            _recorder.kill()
        except Exception:  # noqa: BLE001
            pass
    _recorder = None
    try:
        if os.path.exists(VOICE_FILE) and os.path.getsize(VOICE_FILE) > 100:
            return VOICE_FILE
    except OSError:
        pass
    return None


def _run(command, timeout=180):
    try:
        return subprocess.run(command, capture_output=True, text=True,
                              timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _whisper_cpp(path):
    """whisper.cpp, the lightest of the three."""
    binary = None
    for name in ("whisper-cli", "whisper-cpp", "whisper"):
        if shutil.which(name):
            binary = name
            break
    if not binary or not os.path.exists(WHISPER_MODEL):
        return None
    out = "/tmp/macshell-voice"
    _run([binary, "-m", WHISPER_MODEL, "-f", path, "-nt", "-otxt",
          "-of", out], timeout=300)
    try:
        with open(out + ".txt", encoding="utf-8", errors="replace") as fh:
            text = fh.read().strip()
        return text or None
    except OSError:
        return None


def _whisper_python(path):
    """The openai-whisper command."""
    if not shutil.which("whisper"):
        return None
    out = "/tmp/macshell-whisper"
    os.makedirs(out, exist_ok=True)
    _run(["whisper", path, "--model", "base", "--output_format", "txt",
          "--output_dir", out], timeout=600)
    name = os.path.splitext(os.path.basename(path))[0] + ".txt"
    try:
        with open(os.path.join(out, name), encoding="utf-8",
                  errors="replace") as fh:
            text = fh.read().strip()
        return text or None
    except OSError:
        return None


def _vosk(path):
    """vosk, the offline one with the small models."""
    if not shutil.which("vosk-transcriber"):
        return None
    out = "/tmp/macshell-vosk.txt"
    _run(["vosk-transcriber", "-i", path, "-o", out], timeout=300)
    try:
        with open(out, encoding="utf-8", errors="replace") as fh:
            text = fh.read().strip()
        return text or None
    except OSError:
        return None


def transcribe(path):
    """Turn a recording into text.  Returns (text, error)."""
    if not path or not os.path.exists(path):
        return None, "Nothing was recorded."
    text = _whisper_cpp(path)
    if text is None:
        text = _whisper_python(path)
    if text is None:
        text = _vosk(path)
    if text is None:
        return None, ("No speech recognition found.  Install whisper.cpp "
                      "(pacman -S whisper-cpp) and put a model in "
                      "~/.cache/macshell/ggml-base.bin")
    return text, None


def voice_ready():
    """True when something on the machine can write down the words."""
    if shutil.which("whisper-cli") and os.path.exists(WHISPER_MODEL):
        return True
    return bool(shutil.which("whisper") or shutil.which("vosk-transcriber"))
