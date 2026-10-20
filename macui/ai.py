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
