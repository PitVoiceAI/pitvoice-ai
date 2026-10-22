# acc_online.py
# KI und Spracherkennung über das Internet, kostenlos, ohne die Grafikkarte zu belasten.
#   - Google Gemini (kostenloser API-Schlüssel von aistudio.google.com)
#   - Groq (kostenloser API-Schlüssel von console.groq.com), sehr schnell,
#     kann außerdem die Spracherkennung übernehmen (Whisper)
# Beide sprechen die gleiche "OpenAI-kompatible" Schnittstelle, deshalb reicht ein Programmteil.
#
# Was ins Internet geht: bei der KI deine Frage und die Renndaten (Abstände, Sprit, Zeiten),
# bei der Online-Spracherkennung die Aufnahme deiner Frage. Sonst nichts.
#
# Diese Datei startet man nicht selbst.

import io
import json
import re
import time
import urllib.error
import urllib.request
import uuid
import wave
from acc_sprache import L
import acc_sprache

ANBIETER = {
    "gemini": {"name": "Google Gemini", "adresse": "https://generativelanguage.googleapis.com/v1beta/openai",
               "schluessel_seite": "https://aistudio.google.com/apikey",
               "bevorzugt": [r"^(models/)?gemini-3\.\d-flash$",
                             r"^(models/)?gemini-2\.5-flash$", r"^(models/)?gemini-[\d.]+-flash$",
                             r"^(models/)?gemini-[\d.]+-flash-lite$"]},
    "groq": {"name": "Groq", "adresse": "https://api.groq.com/openai/v1",
             "schluessel_seite": "https://console.groq.com/keys",
             "bevorzugt": [r"^llama-3\.3-70b-versatile$", r"^openai/gpt-oss-120b$", r"^openai/gpt-oss-20b$",
                           r"^qwen/qwen3[.\d]*-\d+b$", r"^llama-3\.1-8b-instant$"]},
}
_modell_cache = {}
_pause_bis = {}          # (anbieter, modell) -> Zeitpunkt, bis zu dem es übersprungen wird (überlastet)


class OnlineFehler(RuntimeError):
    def __init__(self, text, voruebergehend=False):
        super().__init__(text)
        self.voruebergehend = voruebergehend     # überlastet / Limit: ein anderes Modell kann helfen


def _anfrage(anbieter, schluessel, pfad, daten=None, zeitlimit=20.0, roh=None, inhaltstyp="application/json"):
    adresse = ANBIETER[anbieter]["adresse"] + pfad
    if roh is None and daten is not None:
        roh = json.dumps(daten).encode("utf-8")
    kopf = {"Authorization": f"Bearer {schluessel}", "User-Agent": "PitVoice-AI"}
    if roh is not None:
        kopf["Content-Type"] = inhaltstyp
    anfrage = urllib.request.Request(adresse, data=roh, headers=kopf)
    try:
        return urllib.request.urlopen(anfrage, timeout=zeitlimit)
    except urllib.error.HTTPError as fehler:
        text = fehler.read().decode("utf-8", "replace")[:300]
        if fehler.code in (401, 403):
            raise OnlineFehler(L("Der API-Schlüssel stimmt nicht oder ist nicht freigeschaltet.", "The API key is wrong or not activated.")) from None
        name = ANBIETER[anbieter]["name"]
        if fehler.code == 429:
            raise OnlineFehler(L(f"Das kostenlose Limit bei {name} ist gerade erreicht.", f"The free limit at {name} has been reached for now."), True) from None
        if fehler.code in (500, 502, 503, 504):
            raise OnlineFehler(L(f"{name} ist gerade überlastet (passiert bei der kostenlosen Version ab und zu).", f"{name} is overloaded right now (happens now and then on the free tier)."),
                               True) from None
        raise OnlineFehler(L(f"Fehler {fehler.code}: {text}", f"Error {fehler.code}: {text}")) from None
    except urllib.error.URLError as fehler:
        raise OnlineFehler(L(f"Keine Verbindung zu {ANBIETER[anbieter]['name']}: {fehler.reason}", f"No connection to {ANBIETER[anbieter]['name']}: {fehler.reason}"), True) from None
    except TimeoutError:
        raise OnlineFehler(L(f"{ANBIETER[anbieter]['name']} antwortet gerade nicht.", f"{ANBIETER[anbieter]['name']} is not responding right now."), True) from None


def modelle_waehlen(anbieter, schluessel):
    """Die passenden Modelle, das beste zuerst (schnell, gut auf Deutsch). Die weiteren sind
    Ausweich-Modelle, falls das erste gerade überlastet ist."""
    if not schluessel:
        raise OnlineFehler(L(f"Noch kein {ANBIETER[anbieter]['name']}-Schlüssel eingetragen (Einstellungen).", f"No {ANBIETER[anbieter]['name']} key entered yet (settings)."))
    if (anbieter, schluessel) in _modell_cache:
        return _modell_cache[(anbieter, schluessel)]
    with _anfrage(anbieter, schluessel, "/models", zeitlimit=10) as antwort:
        namen = [m.get("id", "") for m in json.load(antwort).get("data", [])]
    modelle = []
    for muster in ANBIETER[anbieter]["bevorzugt"]:
        passend = sorted((n for n in namen if re.search(muster, n)), reverse=True)
        for kandidat in passend[:2]:
            kandidat = kandidat.replace("models/", "")
            if kandidat not in modelle:
                modelle.append(kandidat)
    if not modelle:
        raise OnlineFehler(L("Kein passendes Modell gefunden. Verfügbar: ", "No suitable model found. Available: ") + ", ".join(namen[:8]))
    _modell_cache[(anbieter, schluessel)] = modelle[:4]
    return modelle[:4]


def modell_waehlen(anbieter, schluessel):
    return modelle_waehlen(anbieter, schluessel)[0]


def chat_mit_ausweich(ziele, nachrichten, max_tokens=350, zeitlimit=20.0, melden=None):
    """Wie chat_stueckweise, aber wenn ein Modell überlastet ist oder das Limit erreicht hat,
    wird automatisch das nächste probiert (erst beim selben Anbieter, dann beim anderen).
    ziele: Liste von (anbieter, schluessel)."""
    letzter = None
    for anbieter, schluessel in ziele:
        if not schluessel:
            continue
        try:
            modelle = modelle_waehlen(anbieter, schluessel)
        except OnlineFehler as fehler:
            letzter = fehler
            continue
        frei = [m for m in modelle if _pause_bis.get((anbieter, m), 0) < time.monotonic()] or modelle[:1]
        for modell in frei:
            geliefert = False
            try:
                for stueck in chat_stueckweise(anbieter, schluessel, modell, nachrichten, max_tokens, zeitlimit):
                    geliefert = True
                    yield stueck
                if geliefert:
                    if melden and (anbieter, modell) != (ziele[0][0], modelle_waehlen(*ziele[0])[0]):
                        melden(L(f"Ausgewichen auf {ANBIETER[anbieter]['name']} ({modell}).", f"Switched to {ANBIETER[anbieter]['name']} ({modell})."))
                    return
                letzter = OnlineFehler(L(f"{modell} hat leer geantwortet.", f"{modell} gave an empty answer."), True)
            except OnlineFehler as fehler:
                if geliefert or not fehler.voruebergehend:
                    raise
                letzter = fehler
            _pause_bis[(anbieter, modell)] = time.monotonic() + 120     # 2 Minuten in Ruhe lassen
    raise letzter or OnlineFehler(L("Kein Online-KI-Schlüssel eingetragen.", "No online AI key entered."))


def pruefen(anbieter, schluessel):
    """Gibt (True, modell) oder (False, fehlertext) zurück."""
    if not schluessel:
        return False, L("Noch kein API-Schlüssel eingetragen.", "No API key entered yet.")
    try:
        modelle = modelle_waehlen(anbieter, schluessel)
        besetzt = []
        for modell in modelle:
            start = time.monotonic()
            try:
                text = "".join(chat_stueckweise(anbieter, schluessel, modell,
                                                [{"role": "user", "content": L("Antworte nur mit: Funk-Check okay.", "Reply only with: radio check okay.")}],
                                                max_tokens=60, zeitlimit=20))
            except OnlineFehler as fehler:
                if not fehler.voruebergehend:
                    raise
                besetzt.append(modell)
                _pause_bis[(anbieter, modell)] = time.monotonic() + 120
                continue
            if not text.strip():
                besetzt.append(modell)
                continue
            zusatz = L(f", {', '.join(besetzt)} gerade überlastet", f", {', '.join(besetzt)} overloaded right now") if besetzt else ""
            return True, f"{modell} ({time.monotonic() - start:.1f} s{zusatz})"
        return False, (L(f"{ANBIETER[anbieter]['name']} ist gerade überlastet oder am Limit. Fritz weicht beim "
                       f"Fahren automatisch auf den anderen Anbieter aus, wenn du dort einen Schlüssel hast.", f"{ANBIETER[anbieter]['name']} is overloaded or at its limit right now. While driving, the engineer automatically "
                       f"switches to the other provider if you have a key there."))
    except OnlineFehler as fehler:
        return False, str(fehler)
    except Exception as fehler:
        return False, f"{type(fehler).__name__}: {fehler}"


def _denk_einstellungen(anbieter, modell):
    """Manche Modelle "denken" erst nach, bevor sie antworten. Das kostet Zeit und Platz.
    Hier wird das Nachdenken so kurz wie möglich gestellt."""
    if anbieter == "gemini":
        return {"reasoning_effort": "low"}
    if "gpt-oss" in modell:
        return {"reasoning_effort": "low", "include_reasoning": False}
    if "qwen" in modell:
        return {"reasoning_effort": "none", "reasoning_format": "hidden"}
    return {}


def chat_stueckweise(anbieter, schluessel, modell, nachrichten, max_tokens=350, zeitlimit=20.0, temperatur=0.3):
    """Fragt die KI und liefert die Antwort in kleinen Stücken (Streaming)."""
    denken = _denk_einstellungen(anbieter, modell)
    # Nachdenken zählt bei manchen Modellen mit zur Länge, deshalb dann mehr Platz lassen
    anfrage = {"model": modell, "messages": nachrichten, "stream": True, "temperature": temperatur,
               "max_tokens": max_tokens + (800 if denken and anbieter == "groq" else 0), **denken}
    try:
        antwort = _anfrage(anbieter, schluessel, "/chat/completions", anfrage, zeitlimit=zeitlimit)
    except OnlineFehler as fehler:
        if denken and "400" in str(fehler):
            for k in denken:                          # Modell kennt die Einstellung nicht: ohne nochmal
                anfrage.pop(k, None)
            antwort = _anfrage(anbieter, schluessel, "/chat/completions", anfrage, zeitlimit=zeitlimit)
        else:
            raise
    im_denken = False
    puffer = ""
    with antwort:
        for zeile in antwort:
            zeile = zeile.decode("utf-8", "replace").strip()
            if not zeile.startswith("data:"):
                continue
            inhalt = zeile[5:].strip()
            if inhalt == "[DONE]":
                break
            try:
                stueck = json.loads(inhalt)
            except ValueError:
                continue
            for wahl in stueck.get("choices", []):
                text = (wahl.get("delta") or {}).get("content")
                if not text:
                    continue
                # falls das Modell sein Nachdenken doch mitschickt: <think> ... </think> weglassen
                puffer += text
                while puffer:
                    if im_denken:
                        ende = puffer.find("</think>")
                        if ende < 0:
                            puffer = puffer[-8:]
                            break
                        puffer = puffer[ende + 8:]
                        im_denken = False
                    else:
                        start = puffer.find("<think>")
                        if start >= 0:
                            if start:
                                yield puffer[:start]
                            puffer = puffer[start + 7:]
                            im_denken = True
                        elif "<" in puffer[-7:]:      # vielleicht beginnt gerade "<think>"
                            teil = puffer.rfind("<")
                            if puffer[:teil]:
                                yield puffer[:teil]
                            puffer = puffer[teil:]
                            break
                        else:
                            yield puffer
                            puffer = ""
    if puffer and not im_denken:
        yield puffer


# ---------------------------------------------------------------------------
# Spracherkennung über Groq (Whisper large v3 turbo)
# ---------------------------------------------------------------------------
def _wav_bytes(audio, rate=16000):
    import numpy as np
    puffer = io.BytesIO()
    with wave.open(puffer, "wb") as datei:
        datei.setnchannels(1)
        datei.setsampwidth(2)
        datei.setframerate(rate)
        datei.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return puffer.getvalue()


def erkennen(schluessel, audio, rate=16000, hinweis="", zeitlimit=8.0):
    """Wandelt die Aufnahme (numpy, 16 kHz) über Groq in Text um."""
    grenze = uuid.uuid4().hex
    teile = []

    def feld(name, wert):
        teile.append(f"--{grenze}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{wert}\r\n".encode("utf-8"))

    feld("model", "whisper-large-v3-turbo")
    feld("language", acc_sprache.SPRACHE)
    feld("temperature", "0")
    feld("response_format", "json")
    if hinweis:
        feld("prompt", hinweis[:800])
    teile.append(f"--{grenze}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"funk.wav\"\r\n"
                 f"Content-Type: audio/wav\r\n\r\n".encode("utf-8") + _wav_bytes(audio, rate) + b"\r\n")
    teile.append(f"--{grenze}--\r\n".encode("utf-8"))
    with _anfrage("groq", schluessel, "/audio/transcriptions", roh=b"".join(teile),
                  inhaltstyp=f"multipart/form-data; boundary={grenze}", zeitlimit=zeitlimit) as antwort:
        return json.load(antwort).get("text", "").strip()
