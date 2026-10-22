# acc_qwen.py
# Premium-Stimme mit Qwen3-TTS: klingt sehr natürlich, läuft kostenlos und lokal auf deiner
# Grafikkarte (über llama.cpp mit Vulkan, das funktioniert auch mit AMD-Karten).
#
# Was hier passiert:
#   einrichten(): lädt einmalig herunter (zusammen etwa 1,6 GB)
#       - llama.cpp für Windows mit Vulkan (das Programm, das das Modell ausführt)
#       - das Qwen3-TTS-Modell (Q4_K_M, etwa 1 GB) und den Audio-Teil (mmproj, etwa 450 MB)
#     und erzeugt eine kurze Referenz-Aufnahme, deren Stimmklang Qwen übernimmt.
#   QwenStimme: verwandelt Text in Sprache.
#
# Eigene Stimme: Leg eine saubere Aufnahme (5 bis 15 Sekunden, nur eine Person, kein Hall)
# als stimmen/qwen3/sprecher.wav ab. Dann klingt der Ingenieur wie diese Person.
# Wichtig: Nur die eigene Stimme oder die Stimme einer Person nehmen, die ausdrücklich zugestimmt hat.
#
# Diese Datei startet man nicht selbst.

import glob
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
import wave
import zipfile

import numpy as np

import acc_sprache
from acc_sprache import L

ORDNER = os.path.dirname(os.path.abspath(__file__))
QWEN_ORDNER = os.path.join(ORDNER, "stimmen", "qwen3")
LLAMA_ORDNER = os.path.join(QWEN_ORDNER, "llama")
CACHE_ORDNER = os.path.join(QWEN_ORDNER, "cache")
SPRECHER = os.path.join(QWEN_ORDNER, "sprecher.wav")
HF_REPO = "ggml-org/Qwen3-TTS-12Hz-1.7B-Base-GGUF"
MODELL = "Qwen3-TTS-12Hz-1.7B-Base-Q4_K_M.gguf"
MMPROJ = "mmproj-Qwen3-TTS-12Hz-1.7B-Base-Q8_0.gguf"
GITHUB_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases"
REFERENZ_TEXT = ("Hallo, hier ist dein Renningenieur. Die Reifen sind jetzt warm, und der Abstand "
                 "zum Vordermann beträgt eins Komma vier Sekunden. Konzentrier dich auf saubere Runden.")
KEIN_FENSTER = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _llama_tts():
    treffer = glob.glob(os.path.join(LLAMA_ORDNER, "**", "llama-tts.exe"), recursive=True)
    return treffer[0] if treffer else None


def installiert():
    return (os.path.exists(os.path.join(QWEN_ORDNER, MODELL)) and os.path.exists(os.path.join(QWEN_ORDNER, MMPROJ))
            and _llama_tts() is not None and os.path.exists(SPRECHER))


def _anfrage(adresse):
    return urllib.request.urlopen(urllib.request.Request(adresse, headers={"User-Agent": "PitVoice-AI"}),
                                  timeout=60)


def _herunterladen(adresse, ziel, fortschritt=None, text=""):
    if os.path.exists(ziel):
        return
    teil = ziel + ".teil"
    with _anfrage(adresse) as antwort, open(teil, "wb") as datei:
        gesamt = int(antwort.headers.get("Content-Length") or 0)
        geladen = 0
        letzte_meldung = 0
        while True:
            stueck = antwort.read(1 << 20)
            if not stueck:
                break
            datei.write(stueck)
            geladen += len(stueck)
            if fortschritt and gesamt and time.monotonic() - letzte_meldung > 0.5:
                letzte_meldung = time.monotonic()
                fortschritt(f"{text} {geladen * 100 // gesamt} % ({geladen >> 20} von {gesamt >> 20} MB)")
    os.replace(teil, ziel)


def _llama_adresse():
    """Sucht in den neuesten llama.cpp-Versionen das Windows-Paket mit Vulkan."""
    with _anfrage(GITHUB_API + "?per_page=10") as antwort:
        versionen = json.load(antwort)
    for version in versionen:
        for datei in version.get("assets", []):
            name = datei["name"].lower()
            if name.endswith(".zip") and "win" in name and "vulkan" in name and "x64" in name:
                return datei["browser_download_url"], datei["name"]
    raise RuntimeError("Kein passendes llama.cpp-Paket (Windows, Vulkan) gefunden.")


def einrichten(fortschritt=None):
    """Lädt alles herunter und erzeugt die Referenzstimme. fortschritt(text) meldet den Stand."""
    melden = fortschritt or (lambda text: None)
    os.makedirs(QWEN_ORDNER, exist_ok=True)
    # 1. llama.cpp
    if _llama_tts() is None:
        melden("Suche llama.cpp für Vulkan ...")
        adresse, name = _llama_adresse()
        zip_pfad = os.path.join(QWEN_ORDNER, name)
        _herunterladen(adresse, zip_pfad, melden, "Lade llama.cpp ...")
        melden("Entpacke llama.cpp ...")
        if os.path.exists(LLAMA_ORDNER):
            shutil.rmtree(LLAMA_ORDNER, ignore_errors=True)
        with zipfile.ZipFile(zip_pfad) as z:
            z.extractall(LLAMA_ORDNER)
        os.remove(zip_pfad)
        if _llama_tts() is None:
            raise RuntimeError("In diesem llama.cpp-Paket fehlt llama-tts.exe.")
    # 2. Modell
    for datei, text in ((MMPROJ, "Lade Audio-Teil (450 MB) ..."), (MODELL, "Lade Qwen3-TTS-Modell (1 GB) ...")):
        _herunterladen(f"https://huggingface.co/{HF_REPO}/resolve/main/{datei}",
                       os.path.join(QWEN_ORDNER, datei), melden, text)
    # 3. Referenzstimme: deren Klang übernimmt Qwen
    if not os.path.exists(SPRECHER):
        melden(L("Erzeuge die Referenzstimme ...", "Creating the reference voice ..."))
        referenz_erzeugen()
    melden(L("Teste die Stimme ...", "Testing the voice ..."))
    start = time.monotonic()
    audio, rate = QwenStimme().erzeugen(L("Funk-Check. Hörst du mich gut?", "Radio check. Do you read me?"), zeitlimit=180, cache=False)
    if len(audio) < rate * 0.3:
        raise RuntimeError(L("Die Testausgabe war leer.", "The test output was empty."))
    return time.monotonic() - start


def referenz_erzeugen():
    """Referenz aus der Piper-Stimme Thorsten (frei verwendbar). Ohne Piper: Windows-Stimme."""
    from acc_stimme import PiperStimme, WindowsStimme, piper_installiert
    try:
        if piper_installiert("de_DE-thorsten-high"):
            stimme = PiperStimme("de_DE-thorsten-high", 0)
        else:
            stimme = WindowsStimme("", 0)
        audio, rate = stimme.erzeugen(REFERENZ_TEXT)
    except Exception:
        stimme = WindowsStimme("", 0)
        audio, rate = stimme.erzeugen(REFERENZ_TEXT)
    wav_schreiben(SPRECHER, audio, rate)


def wav_schreiben(pfad, audio, rate):
    daten = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(pfad, "wb") as datei:
        datei.setnchannels(1)
        datei.setsampwidth(2)
        datei.setframerate(int(rate))
        datei.writeframes(daten)


def wav_lesen(pfad):
    with wave.open(pfad, "rb") as datei:
        rate = datei.getframerate()
        kanaele = datei.getnchannels()
        breite = datei.getsampwidth()
        roh = datei.readframes(datei.getnframes())
    if breite == 2:
        audio = np.frombuffer(roh, "<i2").astype(np.float32) / 32768
    elif breite == 4:
        audio = np.frombuffer(roh, "<i4").astype(np.float32) / 2147483648
    else:
        audio = (np.frombuffer(roh, np.uint8).astype(np.float32) - 128) / 128
    if kanaele > 1:
        audio = audio.reshape(-1, kanaele).mean(axis=1)
    return audio, rate


class QwenStimme:
    """Qwen3-TTS über llama-tts.exe. Jede Ausgabe startet das Programm einmal (ein paar Sekunden).
    Häufige Sätze (Box, Box, Füllsätze ...) werden zwischengespeichert und kommen dann sofort."""
    neural = True
    ZEITLIMIT = 25.0
    VERSUCHE = (25.0,)               # ein Versuch, danach springt die Ersatzstimme ein
    art = None

    def __init__(self, name="standard", tempo=0):
        self.name = L("Qwen3 – Premium (Grafikkarte)", "Qwen3 – premium (graphics card)")
        self.programm = _llama_tts()
        if not installiert() or self.programm is None:
            raise RuntimeError(L("Die Qwen3-Stimme ist noch nicht eingerichtet.", "The Qwen3 voice is not set up yet."))
        os.makedirs(CACHE_ORDNER, exist_ok=True)
        with open(SPRECHER, "rb") as datei:
            self._sprecher_kennung = hashlib.sha1(datei.read()).hexdigest()[:10]

    def _cache_pfad(self, text):
        schluessel = hashlib.sha1(f"{self._sprecher_kennung}|{text}".encode("utf-8")).hexdigest()[:20]
        return os.path.join(CACHE_ORDNER, schluessel + ".wav")

    def erzeugen(self, text, zeitlimit=None, cache=True):
        pfad = self._cache_pfad(text)
        if cache and os.path.exists(pfad):
            try:
                os.utime(pfad)                   # zuletzt benutzt (für das Aufräumen)
            except OSError:
                pass
            return wav_lesen(pfad)
        ausgabe = os.path.join(tempfile.gettempdir(), f"qwen_{os.getpid()}_{time.monotonic_ns()}.wav")
        befehl = [self.programm, "-m", os.path.join(QWEN_ORDNER, MODELL),
                  "--mmproj", os.path.join(QWEN_ORDNER, MMPROJ),
                  "-p", text, "--tts-lang", "en" if acc_sprache.englisch() else "de", "--tts-speaker-file", SPRECHER,
                  "--output", ausgabe, "-ngl", "99"]
        try:
            ergebnis = subprocess.run(befehl, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                      timeout=zeitlimit or self.ZEITLIMIT, creationflags=KEIN_FENSTER,
                                      cwd=os.path.dirname(self.programm))
            if ergebnis.returncode != 0 or not os.path.exists(ausgabe):
                rest = (ergebnis.stderr or ergebnis.stdout or "").strip().splitlines()[-6:]
                raise RuntimeError("llama-tts hat nicht geklappt: " + " | ".join(rest))
            audio, rate = wav_lesen(ausgabe)
            from acc_stimme import pausen_kuerzen
            audio = pausen_kuerzen(audio, rate, laengste=0.3)
        finally:
            try:
                os.remove(ausgabe)
            except OSError:
                pass
        if cache and len(text) <= 160:          # kurze Sätze merken, die kommen oft wieder
            try:
                wav_schreiben(pfad, audio, rate)
                self._cache_aufraeumen()
            except OSError:
                pass
        return audio, rate

    @staticmethod
    def _cache_aufraeumen(maximal=400):
        dateien = sorted(glob.glob(os.path.join(CACHE_ORDNER, "*.wav")), key=os.path.getmtime)
        for datei in dateien[:-maximal]:
            try:
                os.remove(datei)
            except OSError:
                pass
