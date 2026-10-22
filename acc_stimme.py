# acc_stimme.py
# Die Stimme des Renningenieurs:
#   - Microsoft-Neural-Stimmen (klingen am natürlichsten, kostenlos, brauchen Internet)
#   - Piper-Stimmen (natürlich, kostenlos, offline) oder Windows-Stimmen (schon auf dem PC)
#   - Aussprache-Wörterbuch: ABS, TC, englische Begriffe usw. richtig aussprechen
#   - Funk-Effekt: klingt wie Boxenfunk, bleibt aber gut verständlich
#   - Warteschlange: Ansagen kommen nacheinander, wichtige zuerst
#
# Diese Datei startet man nicht selbst.

import json
import os
import queue
from collections import deque
import re
import threading
import time
import urllib.request

import numpy as np

ORDNER = os.path.dirname(os.path.abspath(__file__))
STIMMEN_ORDNER = os.path.join(ORDNER, "stimmen")

# ---------------------------------------------------------------------------
# 1) Welche Stimmen gibt es?
# Piper-Stimmen werden einmalig heruntergeladen (von huggingface.co).
# ---------------------------------------------------------------------------
from acc_sprache import L
import acc_sprache

# Stimmen-Einträge: (id, Name, Geschlecht "m"/"w", Sprache "de"/"en"/"de+en", Zusatz deutsch, Zusatz englisch)
PIPER_STIMMEN = [
    ("de_DE-thorsten-high", "Thorsten", "m", "de", "beste Qualität", "best quality"),
    ("de_DE-thorsten-medium", "Thorsten", "m", "de", "schneller", "faster"),
    ("de_DE-karlsson-low", "Karlsson", "m", "de", "", ""),
    ("de_DE-kerstin-low", "Kerstin", "w", "de", "", ""),
    ("de_DE-ramona-low", "Ramona", "w", "de", "", ""),
    ("de_DE-eva_k-x_low", "Eva", "w", "de", "sehr schnell", "very fast"),
    ("en_GB-northern_english_male-medium", "Northern English", "m", "en", "britisch", "British"),
]
# Nur Stimmen mit Lizenzen, die eine kostenlose Weitergabe erlauben (siehe DRITTANBIETER.txt).
# Bewusst NICHT dabei: lessac (nur Forschung), ryan und pavoque (nicht kommerziell), alan und amy (Lizenz unklar).
HF_ADRESSE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/{sprache}/{region}/{name}/{qualitaet}/{datei}"


def _anzeige(eintrag):
    """'Florian (männlich, empfohlen) · Deutsch + Englisch'"""
    _, name, geschlecht, sprache, zusatz_de, zusatz_en = eintrag
    teile = [L("männlich", "male") if geschlecht == "m" else L("weiblich", "female")]
    zusatz = L(zusatz_de, zusatz_en)
    if zusatz:
        teile.append(zusatz)
    sprachen = {"de": L("Deutsch", "German"), "en": L("Englisch", "English"),
                "de+en": L("Deutsch + Englisch", "German + English")}[sprache]
    return f"{name} ({', '.join(teile)}) · {sprachen}"


def _name(liste, stimme_id):
    for eintrag in liste:
        if eintrag[0] == stimme_id:
            return eintrag[1]
    return stimme_id

ONECORE_STIMMEN = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices"

# Microsoft-Neural-Stimmen (dieselben wie beim Vorlesen in Microsoft Edge).
# "Multilingual" heißt: Sie sprechen auch englische Begriffe richtig aus.
EDGE_STIMMEN = [
    ("de-DE-FlorianMultilingualNeural", "Florian", "m", "de+en", "empfohlen", "recommended"),
    ("de-DE-SeraphinaMultilingualNeural", "Seraphina", "w", "de+en", "", ""),
    ("de-DE-ConradNeural", "Conrad", "m", "de", "", ""),
    ("de-DE-KillianNeural", "Killian", "m", "de", "", ""),
    ("de-DE-KatjaNeural", "Katja", "w", "de", "", ""),
    ("de-DE-AmalaNeural", "Amala", "w", "de", "", ""),
    ("en-US-AndrewMultilingualNeural", "Andrew", "m", "en", "empfohlen", "recommended"),
    ("en-US-BrianMultilingualNeural", "Brian", "m", "en", "", ""),
    ("en-US-AvaMultilingualNeural", "Ava", "w", "en", "", ""),
    ("en-GB-RyanNeural", "Ryan", "m", "en", "britisch", "British"),
    ("en-GB-ThomasNeural", "Thomas", "m", "en", "britisch", "British"),
    ("en-GB-SoniaNeural", "Sonia", "w", "en", "britisch", "British"),
]
# Standard: frei lizenzierte Piper-Stimmen (laufen ohne Internet). Die Neural-Stimmen nutzen einen
# inoffiziellen Microsoft-Dienst und werden erst nach einem Hinweis freigeschaltet.
STANDARD_STIMME = {"de": "piper:de_DE-thorsten-high", "en": "piper:en_GB-northern_english_male-medium"}
NEURAL_HINWEIS = L("Die Neural-Stimmen nutzen den Vorlese-Dienst von Microsoft Edge. Das ist kein offizieller, "
                   "lizenzierter Zugang: Microsoft kann ihn jederzeit ändern oder abschalten, und die Nutzung "
                   "erfolgt auf eigene Verantwortung. Der Text, der vorgelesen wird, geht dabei an Microsoft.",
                   "The neural voices use the read-aloud service of Microsoft Edge. This is not an official, "
                   "licensed access: Microsoft can change or switch it off at any time, and you use it at your "
                   "own risk. The text that is read out is sent to Microsoft.")


# Pocket TTS von Kyutai: läuft komplett auf deinem PC (ohne Internet), klingt natürlich.
POCKET_STIMMEN = [
    ("juergen", "Jürgen", "m", "de", "ohne Internet", "offline"),
]


def pocket_installiert():
    import importlib.util
    return importlib.util.find_spec("pocket_tts") is not None


def edge_installiert():
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


def _piper_pfad(datei_name):
    return os.path.join(STIMMEN_ORDNER, datei_name + ".onnx")


def piper_installiert(datei_name):
    pfad = _piper_pfad(datei_name)
    return os.path.exists(pfad) and os.path.exists(pfad + ".json")


def windows_stimmen_tokens():
    """Gibt eine Liste von (Name, Stimme) zurück, deutsche Stimmen zuerst."""
    import win32com.client
    quellen = [win32com.client.Dispatch("SAPI.SpVoice").GetVoices()]
    try:
        kategorie = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
        kategorie.SetId(ONECORE_STIMMEN, False)
        quellen.append(kategorie.EnumerateTokens())
    except Exception:
        pass   # gibt es nicht auf jedem PC
    gefunden, namen = [], set()
    for quelle in quellen:
        for i in range(quelle.Count):
            token = quelle.Item(i)
            name = token.GetDescription()
            if name not in namen:
                namen.add(name)
                gefunden.append((name, token))
    deutsch = lambda n: "German" in n or "Deutsch" in n
    gefunden.sort(key=lambda paar: (not deutsch(paar[0]), paar[0]))
    return gefunden


def _passt(sprache):
    """Stimmen der eingestellten Sprache zuerst."""
    return 0 if acc_sprache.SPRACHE in sprache.split("+") else 1


def stimmen_liste():
    """Alle Stimmen als Liste von (id, Anzeigename, installiert).
    Reihenfolge: Piper (Standard, frei lizenziert), Neural (inoffiziell, mit Hinweis), Pocket, Qwen3.
    Innerhalb jeder Art kommen die Stimmen der eingestellten Sprache zuerst.
    Die Windows-Stimmen stehen nicht mehr in der Liste (nur noch als Notfall-Ersatz)."""
    liste = []
    for e in sorted(PIPER_STIMMEN, key=lambda e: _passt(e[3])):
        liste.append((f"piper:{e[0]}", "Piper – " + _anzeige(e), piper_installiert(e[0])))
    edge_da = edge_installiert()
    for e in sorted(EDGE_STIMMEN, key=lambda e: _passt(e[3])):
        liste.append((f"edge:{e[0]}", "Neural – " + _anzeige(e) + L(" · inoffiziell (Microsoft)", " · unofficial (Microsoft)"),
                      edge_da))
    pocket_da = pocket_installiert()
    for e in POCKET_STIMMEN:
        liste.append((f"pocket:{e[0]}", "Pocket – " + _anzeige(e), pocket_da))
    try:
        import acc_qwen
        liste.append(("qwen:standard", L("Qwen3 – Premium, sehr natürlich (Grafikkarte, einmalig 1,6 GB) · Deutsch + Englisch",
                                         "Qwen3 – premium, very natural (graphics card, one-time 1.6 GB) · German + English"),
                      acc_qwen.installiert()))
    except Exception:
        pass
    return liste


def piper_herunterladen(datei_name, fortschritt=None):
    """Lädt eine Piper-Stimme herunter. fortschritt(prozent) wird zwischendurch aufgerufen."""
    os.makedirs(STIMMEN_ORDNER, exist_ok=True)
    teile = datei_name.split("-")              # de_DE, thorsten, high
    region, name, qualitaet = teile[0], teile[1], teile[2]
    for endung, anteil in ((".onnx.json", 0), (".onnx", 1)):
        datei = datei_name + endung
        adresse = HF_ADRESSE.format(sprache=region.split("_")[0], region=region, name=name,
                                    qualitaet=qualitaet, datei=datei)
        ziel = os.path.join(STIMMEN_ORDNER, datei)

        def melden(bloecke, blockgroesse, gesamt):
            if fortschritt and gesamt > 0 and anteil:
                fortschritt(min(100, int(bloecke * blockgroesse * 100 / gesamt)))

        urllib.request.urlretrieve(adresse, ziel + ".teil", melden)
        os.replace(ziel + ".teil", ziel)


# ---------------------------------------------------------------------------
# Aussprache-Wörterbuch
# Die Stimmen lesen Abkürzungen sonst als Wort ("Abs") und englische Begriffe
# mit deutscher Betonung. Wir ersetzen solche Wörter vor dem Sprechen.
# Die Datei aussprache.json im Programmordner kannst du selbst erweitern.
# ---------------------------------------------------------------------------
AUSSPRACHE_DATEI = os.path.join(ORDNER, "aussprache.json")

AUSSPRACHE_STANDARD = {
    "_info": "Links das Wort, rechts wie es gesprochen wird. 'alle' gilt für jede Stimme, "
             "'ohne_neural' nur für Piper- und Windows-Stimmen (die Neural-Stimmen können "
             "Englisch schon). Groß- und Kleinschreibung zählt.",
    "alle": {
        "TC-Cut": "T C Cut",
        "TC": "T C",
        "ABS": "A B S",
        "PSI": "P S I",
        "KI": "K I",
        "ACC": "A C C",
        "km/h": "Kilometer pro Stunde",
        "Copy": "Koppi",                 # sonst sagen manche Stimmen "Kapi"
        "copy": "Koppi",
    },
    "ohne_neural": {
        "Renningenieur": "Renn-Inschenjör",
        "Ingenieur": "Inschenjör",
        "Pitlimiter": "Pitt-Limitter",
        "Track Limits": "Träck Limmits",
        "Lift and Coast": "Lift änd Kohst",
        "Stop and Go": "Stopp änd Go",
        "Motor-Map": "Motor-Mäpp",
        "Cut": "Katt",
        "Funk-Check": "Funk-Tscheck",
        "Superpole": "Super-Pohl",
        "Qualifying": "Kwalifeiing",
        "Hotlap": "Hott-Läpp",
        "Stint": "Stint",
        "Push": "Pusch",
        "Safety Car": "Sejfti Kahr",
        "Leader": "Lieder",
    },
}

_aussprache = None


def aussprache_laden():
    """Lädt aussprache.json. Fehlt die Datei, wird sie mit den Standardwerten angelegt."""
    global _aussprache
    daten = json.loads(json.dumps(AUSSPRACHE_STANDARD))
    try:
        with open(AUSSPRACHE_DATEI, encoding="utf-8") as datei:
            eigene = json.load(datei)
        for gruppe in ("alle", "ohne_neural"):
            daten[gruppe].update(eigene.get(gruppe, {}))
    except (OSError, ValueError):
        try:
            with open(AUSSPRACHE_DATEI, "w", encoding="utf-8") as datei:
                json.dump(AUSSPRACHE_STANDARD, datei, indent=2, ensure_ascii=False)
        except OSError:
            pass
    _aussprache = daten
    return daten


_EINER = ["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn",
          "elf", "zwölf", "dreizehn", "vierzehn", "fünfzehn", "sechzehn", "siebzehn", "achtzehn",
          "neunzehn"]
_ZEHNER = ["", "", "zwanzig", "dreißig", "vierzig", "fünfzig", "sechzig", "siebzig", "achtzig", "neunzig"]
_BUCHSTABEN = {"A": "Ah", "B": "Be", "C": "Ze", "D": "De", "E": "Eh", "F": "Eff", "G": "Ge", "H": "Ha",
               "I": "I", "J": "Jott", "K": "Ka", "L": "Ell", "M": "Emm", "N": "Enn", "O": "Oh", "P": "Pe",
               "Q": "Ku", "R": "Er", "S": "Es", "T": "Te", "U": "U", "V": "Fau", "W": "We", "X": "Ix",
               "Y": "Üpsilon", "Z": "Zett"}


def zahlwort(zahl):
    """Ganze Zahl als deutsches Wort: 21 -> 'einundzwanzig'."""
    if zahl < 20:
        return _EINER[zahl]
    if zahl < 100:
        zehner, einer = divmod(zahl, 10)
        return (("ein" if einer == 1 else _EINER[einer]) + "und" if einer else "") + _ZEHNER[zehner]
    if zahl < 1000:
        hundert, rest = divmod(zahl, 100)
        return ("ein" if hundert == 1 else _EINER[hundert]) + "hundert" + (zahlwort(rest) if rest else "")
    if zahl < 1_000_000:
        tausend, rest = divmod(zahl, 1000)
        return ("ein" if tausend == 1 else zahlwort(tausend)) + "tausend" + (zahlwort(rest) if rest else "")
    return str(zahl)


def _zahlen_ausschreiben(text):
    """'1,4' -> 'eins Komma vier', '13' -> 'dreizehn'. Für Stimmen, die Ziffern nicht gut lesen."""
    text = re.sub(r"(\d+),(\d+)", lambda m: f"{zahlwort(int(m.group(1)))} Komma "
                  + " ".join(zahlwort(int(z)) for z in m.group(2)), text)
    text = re.sub(r"\d+", lambda m: zahlwort(int(m.group(0))), text)
    return text.replace("%", " Prozent")


def _einheiten_englisch(text):
    """Einheiten ganz aussprechen: '26 psi' -> 'pounds per square inch' (beim ersten Mal, danach nur die Zahl,
    so wie ein Ingenieur das sagt), '24 °C' / '24 degrees C' -> '24 degrees Celsius'."""
    text = re.sub(r"(\d)\s*°\s*C\b", r"\1 degrees Celsius", text)
    text = re.sub(r"\bdeg(?:rees?|\.)?\s*C\b(?!elsius)", "degrees Celsius", text, flags=re.I)
    text = re.sub(r"(\d)\s*°\s*F\b", r"\1 degrees Fahrenheit", text)
    text = re.sub(r"(\d)\s*°", r"\1 degrees", text)
    erstes = [True]

    def psi(treffer):
        if erstes[0]:
            erstes[0] = False
            return treffer.group(1) + " pounds per square inch"
        return treffer.group(1)
    text = re.sub(r"(\d)\s*psi\b", psi, text, flags=re.I)
    return re.sub(r"\bpsi\b", "pounds per square inch", text, flags=re.I)


def aussprechen(text, neural=False, art=None):
    """Bereitet den Text fürs Sprechen vor (nur für die Stimme, nicht fürs Protokoll).
    neural=True: Neural-Stimmen (können Englisch selbst).
    art="pocket": KI-Stimme, die echte Wörter braucht (keine Ziffern, keine Lautschrift)."""
    daten = _aussprache or aussprache_laden()
    if acc_sprache.englisch():
        # Englisch: nur Abkürzungen buchstabieren, die deutsche Lautschrift passt hier nicht
        text = _einheiten_englisch(text)
        ersetzungen = {"TC-Cut": "T C cut", "TC": "T C", "ABS": "A B S", "ACC": "A C C",
                       "km/h": "kilometres per hour", "AI": "A I"}
        for wort in sorted(ersetzungen, key=len, reverse=True):
            text = re.sub(r"(?<![\w-])" + re.escape(wort) + r"(?![\w])", ersetzungen[wort], text)
        return re.sub(r"\bP(\d{1,2})\b", r"P \1", text)
    text = re.sub(r"(\d)\s*°\s*C\b", r"\1 Grad Celsius", text)
    text = re.sub(r"(\d)\s*°", r"\1 Grad", text)
    ersetzungen = dict(daten["alle"])
    if not neural and art != "pocket":
        ersetzungen.update(daten["ohne_neural"])
    # Längere Begriffe zuerst, damit "TC-Cut" vor "TC" drankommt
    for wort in sorted(ersetzungen, key=len, reverse=True):
        text = re.sub(r"(?<![\w-])" + re.escape(wort) + r"(?![\w])", ersetzungen[wort], text)
    # P3 -> "P 3", damit es als Buchstabe P gesprochen wird
    text = re.sub(r"\bP(\d{1,2})\b", r"P \1", text)
    if art == "pocket":
        # Einzelne Großbuchstaben ("A B S", "P 3") als Buchstabennamen: "Ah-Be-Es", "Pe drei"
        text = re.sub(r"\b[A-Z](?: [A-Z])*\b(?![a-zäöüß])",
                      lambda m: "-".join(_BUCHSTABEN[b] for b in m.group(0).split()), text)
        text = _zahlen_ausschreiben(text)
    return text


# ---------------------------------------------------------------------------
# 2) Text in Ton verwandeln
# Beide Stimmenarten liefern eine Zahlenreihe (Audio) und die Abtastrate.
# ---------------------------------------------------------------------------
class WindowsStimme:
    def __init__(self, name, tempo):
        import win32com.client
        self.stimme = win32com.client.Dispatch("SAPI.SpVoice")
        tokens = windows_stimmen_tokens()
        auswahl = [t for n, t in tokens if n == name] or \
                  [t for n, t in tokens if "German" in n or "Deutsch" in n]
        if auswahl:
            try:
                self.stimme.Voice = auswahl[0]
            except Exception:
                pass
        self.stimme.Rate = int(tempo)
        self.name = self.stimme.Voice.GetDescription()

    def erzeugen(self, text):
        import win32com.client
        # Statt direkt abzuspielen, schreibt die Stimme in einen Speicher.
        # So können wir den Funk-Effekt darüberlegen.
        strom = win32com.client.Dispatch("SAPI.SpMemoryStream")
        format_ = win32com.client.Dispatch("SAPI.SpAudioFormat")
        format_.Type = 22                     # 22.050 Hz, 16 Bit, Mono
        strom.Format = format_
        self.stimme.AudioOutputStream = strom
        self.stimme.Speak(text)
        roh = bytes(strom.GetData())
        return np.frombuffer(roh, dtype=np.int16).astype(np.float32) / 32768, 22050


class PiperStimme:
    def __init__(self, datei_name, tempo):
        from piper import PiperVoice
        self.stimme = PiperVoice.load(_piper_pfad(datei_name))
        try:
            from piper import SynthesisConfig
        except ImportError:
            from piper.config import SynthesisConfig
        # Tempo -5 bis 10 wie bei Windows. Höher = schneller = kürzere Länge.
        self.einstellung = SynthesisConfig(length_scale=0.94 ** int(tempo))
        self.name = "Piper – " + _name(PIPER_STIMMEN, datei_name)

    def erzeugen(self, text):
        teile, rate = [], 22050
        for stueck in self.stimme.synthesize(text, syn_config=self.einstellung):
            rate = stueck.sample_rate
            teile.append(np.frombuffer(stueck.audio_int16_bytes, dtype=np.int16))
        if not teile:
            return np.zeros(1, dtype=np.float32), rate
        return np.concatenate(teile).astype(np.float32) / 32768, rate


def mp3_entpacken(daten, rate=24000):
    """Wandelt MP3-Daten in eine Zahlenreihe um (mit dem Paket av, das faster-whisper mitbringt)."""
    import io

    import av
    teile = []

    def sammeln(stuecke):
        if stuecke is None:
            return
        if not isinstance(stuecke, (list, tuple)):
            stuecke = [stuecke]
        for stueck in stuecke:
            teile.append(stueck.to_ndarray().reshape(-1))

    with av.open(io.BytesIO(daten), mode="r") as datei:
        umwandler = av.AudioResampler(format="s16", layout="mono", rate=rate)
        for rahmen in datei.decode(audio=0):
            sammeln(umwandler.resample(rahmen))
        try:
            sammeln(umwandler.resample(None))       # Rest aus dem Zwischenspeicher holen
        except Exception:
            pass
    if not teile:
        raise RuntimeError("Leere Audiodaten vom Sprachdienst")
    return np.concatenate(teile).astype(np.float32) / 32768


class EdgeStimme:
    """Microsoft-Neural-Stimme. Der Text wird übers Internet in Sprache verwandelt."""
    neural = True
    ZEITLIMIT = 3.5          # länger warten wir nicht, sonst springt die Ersatzstimme ein

    def __init__(self, name, tempo):
        import asyncio

        import edge_tts  # noqa: F401  (prüft, ob installiert)
        self.stimme = name
        self.tempo = f"{int(tempo) * 5:+d}%"           # Tempo 2 -> "+10%"
        self.name = "Neural – " + _name(EDGE_STIMMEN, name)
        self._schleife = asyncio.new_event_loop()       # einmal anlegen statt jedes Mal neu

    def erzeugen(self, text, zeitlimit=None):
        import asyncio

        import edge_tts

        async def holen():
            daten = bytearray()
            async for stueck in edge_tts.Communicate(text, self.stimme, rate=self.tempo).stream():
                if stueck["type"] == "audio":
                    daten += stueck["data"]
            return bytes(daten)

        daten = self._schleife.run_until_complete(asyncio.wait_for(holen(), timeout=zeitlimit or self.ZEITLIMIT))
        if not daten:
            raise RuntimeError("Keine Antwort vom Sprachdienst")
        return mp3_entpacken(daten, 24000), 24000


def pausen_kuerzen(audio, rate, laengste=0.18, rand=0.03):
    """Kürzt lange Stille zwischen Wörtern/Sätzen und am Anfang und Ende."""
    if len(audio) < rate * 0.1:
        return audio
    rahmen = int(rate * 0.01)
    anzahl = len(audio) // rahmen
    pegel = np.sqrt(np.mean(audio[:anzahl * rahmen].reshape(anzahl, rahmen) ** 2, axis=1))
    still = pegel < max(pegel.max() * 0.03, 1e-4)
    behalten = np.ones(anzahl, dtype=bool)
    max_rahmen = int(laengste / 0.01)
    rand_rahmen = int(rand / 0.01)
    i = 0
    while i < anzahl:
        if still[i]:
            j = i
            while j < anzahl and still[j]:
                j += 1
            erlaubt = rand_rahmen if (i == 0 or j == anzahl) else max_rahmen
            if j - i > erlaubt:
                # die Mitte der Pause rausnehmen, Ränder behalten (klingt natürlicher)
                weg = (j - i) - erlaubt
                anfang = i + (erlaubt // 2 if 0 < i and j < anzahl else (0 if i == 0 else erlaubt))
                behalten[anfang:anfang + weg] = False
            i = j
        else:
            i += 1
    teile = audio[:anzahl * rahmen].reshape(anzahl, rahmen)[behalten].reshape(-1)
    return np.concatenate([teile, audio[anzahl * rahmen:]]).astype(np.float32)


def zeitstrecken(audio, rate, faktor):
    """Macht Sprache schneller (faktor > 1) oder langsamer, ohne die Tonhöhe zu ändern.
    Verfahren: WSOLA. Kleine überlappende Stücke werden neu zusammengesetzt, jeweils an der
    Stelle, die am besten zum vorigen Stück passt."""
    if abs(faktor - 1) < 0.02 or len(audio) < rate * 0.1:
        return audio
    fenster = int(rate * 0.03)
    schritt_aus = fenster // 2
    schritt_ein = int(round(schritt_aus * faktor))
    spiel = int(rate * 0.008)
    huelle = np.hanning(fenster).astype(np.float32)
    x = np.concatenate([np.zeros(spiel, np.float32), audio.astype(np.float32),
                        np.zeros(fenster + spiel + schritt_ein, np.float32)])
    laenge_aus = int(len(audio) / faktor) + fenster
    y = np.zeros(laenge_aus + fenster, np.float32)
    gewicht = np.zeros_like(y)
    pos_ein, pos_aus, vorher = spiel, 0, None
    while pos_ein + fenster + spiel < len(x) and pos_aus + fenster <= len(y):
        if vorher is None:
            beste = pos_ein
        else:
            vorbild = x[vorher + schritt_aus: vorher + schritt_aus + fenster]
            bereich = x[pos_ein - spiel: pos_ein + spiel + fenster]
            aehnlichkeit = np.correlate(bereich, vorbild, mode="valid")
            beste = pos_ein - spiel + int(np.argmax(aehnlichkeit))
        y[pos_aus:pos_aus + fenster] += x[beste:beste + fenster] * huelle
        gewicht[pos_aus:pos_aus + fenster] += huelle
        vorher = beste
        pos_ein += schritt_ein
        pos_aus += schritt_aus
    y = y / np.maximum(gewicht, 1e-3)
    return y[:int(len(audio) / faktor)].astype(np.float32)


class _Utf8Dateien:
    """Pocket TTS liest unter Windows seine Einstellungsdateien mit der falschen
    Zeichenkodierung (Fehler im Paket). Solange Pocket lädt, öffnen wir Textdateien
    deshalb ausdrücklich als UTF-8."""

    def __enter__(self):
        import builtins
        import io
        self._original = builtins.open

        def oeffnen(datei, mode="r", buffering=-1, encoding=None, *rest, **mehr):
            if "b" not in mode and encoding is None:
                encoding = "utf-8"
            return self._original(datei, mode, buffering, encoding, *rest, **mehr)

        builtins.open = io.open = oeffnen
        return self

    def __exit__(self, *fehler):
        import builtins
        import io
        builtins.open = io.open = self._original
        return False


class PocketStimme:
    """Pocket TTS: moderne KI-Stimme, die auf dem Prozessor läuft. Kein Internet nötig."""
    neural = False
    art = "pocket"

    def __init__(self, name, tempo):
        import torch
        from pocket_tts import TTSModel
        torch.set_num_threads(4)                       # ACC soll genug Prozessor übrig haben
        with _Utf8Dateien():
            self.modell = TTSModel.load_model(language="german")
            self.zustand = self.modell.get_state_for_audio_prompt(name)
        self.rate = self.modell.sample_rate
        self.name = "Pocket – " + _name(POCKET_STIMMEN, name)
        # Pocket hat keine eigene Tempo-Einstellung. Wir kürzen Pausen und strecken die Zeit:
        # Regler 0 = normal, 10 = etwa 35 % schneller, -5 = etwa 17 % langsamer
        self.faktor = 1 + int(tempo) * 0.035

    def erzeugen(self, text):
        audio = self.modell.generate_audio(self.zustand, text)
        audio = audio.detach().cpu().numpy().astype(np.float32).reshape(-1)
        audio = pausen_kuerzen(audio, self.rate)
        audio = zeitstrecken(audio, self.rate, self.faktor)
        return audio, self.rate


def acc_stimme_sprache():
    return "en" if acc_sprache.englisch() else "de"


def ersatz_laden(tempo):
    """Offline-Stimme für den Notfall: eine geladene Piper-Stimme, sonst Windows."""
    for datei in sorted((e[0] for e in PIPER_STIMMEN), key=lambda d: 0 if d.startswith(acc_stimme_sprache()) else 1):
        if piper_installiert(datei):
            try:
                return PiperStimme(datei, tempo)
            except Exception:
                break
    return WindowsStimme("", tempo)


def stimme_laden(stimme_id, tempo):
    """Lädt die gewünschte Stimme. Fällt auf eine Windows-Stimme zurück, wenn es nicht klappt."""
    if stimme_id.startswith("qwen:"):
        import acc_qwen
        return acc_qwen.QwenStimme(stimme_id[len("qwen:"):], tempo)
    if stimme_id.startswith("edge:"):
        return EdgeStimme(stimme_id[len("edge:"):], tempo)
    if stimme_id.startswith("pocket:"):
        return PocketStimme(stimme_id[len("pocket:"):], tempo)
    if stimme_id.startswith("piper:"):
        datei = stimme_id[len("piper:"):]
        if piper_installiert(datei):
            return PiperStimme(datei, tempo)
    name = stimme_id[len("windows:"):] if stimme_id.startswith("windows:") else stimme_id
    return WindowsStimme(name, tempo)


# ---------------------------------------------------------------------------
# 3) Funk-Effekt
# Echter Boxenfunk überträgt nur die mittleren Frequenzen (keine tiefen Bässe,
# keine hohen Zischlaute), ist etwas übersteuert und rauscht leicht.
# Dazu kommt das Klicken beim Drücken und Loslassen der Sprechtaste.
# ---------------------------------------------------------------------------
FUNK_STUFEN = ["aus", "leicht", "mittel", "stark"]
_FUNK_WERTE = {
    # Stufe: (untere Grenze Hz, obere Grenze Hz, Übersteuerung, Rauschen)
    1: (200, 5000, 1.6, 0.006),
    2: (300, 3800, 2.6, 0.012),
    3: (420, 3000, 4.0, 0.022),
}


def _bandpass(signal, rate, tief, hoch):
    anzahl = len(signal)
    spektrum = np.fft.rfft(signal)
    f = np.maximum(np.fft.rfftfreq(anzahl, 1 / rate), 1.0)
    maske = 1 / np.sqrt(1 + (tief / f) ** 8) / np.sqrt(1 + (f / hoch) ** 8)
    maske *= 1 + 0.5 * np.exp(-((f - 2000) / 700) ** 2)   # Sprache etwas nach vorne holen
    return np.fft.irfft(spektrum * maske, anzahl)


def _glocke(rate, frequenz, dauer, lautstaerke):
    """Ein weicher Glockenton: sanft rein, langsam ausklingen, ohne Knacken."""
    t = np.arange(int(rate * dauer)) / rate
    ton = np.sin(2 * np.pi * frequenz * t) + 0.25 * np.sin(2 * np.pi * frequenz * 2 * t)
    huelle = np.minimum(1, t / 0.006) * np.exp(-t / (dauer / 4))      # 6 ms Anstieg
    huelle[-int(rate * 0.01):] *= np.linspace(1, 0, int(rate * 0.01))  # ganz weich enden
    return ton * huelle * lautstaerke / 1.25


def funk_ton(rate, stufe=2, ende=False):
    """Das 'ba-ding' vor jedem Funkspruch, wie bei einem Walkie-Talkie.
    ende=True: umgekehrt ('ding-ba'), wenn der Funkspruch vorbei ist."""
    tief, hoch, _, rauschen = _FUNK_WERTE.get(stufe, _FUNK_WERTE[2])
    tiefer_ton, hoher_ton = 784, 1175                 # G und D, eine Quinte auseinander
    erster, zweiter = (hoher_ton, tiefer_ton) if ende else (tiefer_ton, hoher_ton)
    ba = _glocke(rate, erster, 0.16, 0.22)
    ding = _glocke(rate, zweiter, 0.30, 0.26)
    abstand = int(rate * 0.085)
    ton = np.zeros(abstand + len(ding))
    ton[:len(ba)] += ba
    ton[abstand:] += ding

    # Funkrauschen darunter: kommt mit dem Ton und klingt mit ihm aus
    zufall = np.random.default_rng()
    hauch = _bandpass(zufall.standard_normal(len(ton)), rate, tief, hoch)
    hauch /= np.max(np.abs(hauch)) + 1e-9
    t = np.arange(len(ton)) / rate
    huelle = np.minimum(1, t / 0.015) * np.exp(-t / 0.25)
    ton = ton + hauch * huelle * (0.05 + rauschen * 2)
    # Der Ton läuft auch durch den Funk-Filter, damit er nach Funk klingt
    ton = _bandpass(ton, rate, tief * 0.8, hoch * 1.2)
    ton *= 0.26 / (np.max(np.abs(ton)) + 1e-9)
    blende = int(rate * 0.008)                        # weicher Anfang und Ende, kein Knacken
    ton[:blende] *= np.linspace(0, 1, blende)
    ton[-blende:] *= np.linspace(1, 0, blende)
    return ton


def funk_knacken(rate, stufe=2, ende=False):
    """Kurzes, leichtes Knacken und Rauschen wie bei einem Funkgerät,
    am Anfang (ende=False) und am Ende (ende=True) eines Funkspruchs des Ingenieurs."""
    tief, hoch, _, _ = _FUNK_WERTE.get(stufe, _FUNK_WERTE[2])
    zufall = np.random.default_rng()
    dauer = 0.24 if ende else 0.18
    n = int(rate * dauer)
    t = np.arange(n) / rate
    rauschen = _bandpass(zufall.standard_normal(n), rate, tief, hoch)
    rauschen /= np.max(np.abs(rauschen)) + 1e-9
    if ende:
        huelle = np.minimum(1, t / 0.01) * np.exp(-t / 0.075)    # "kschhh" klingt aus
    else:
        # Am Anfang sanft: weich einblenden (30 ms), dann ruhig in die Stimme übergehen
        einblenden = np.clip(t / 0.03, 0, 1) ** 2
        huelle = einblenden * np.exp(-np.maximum(0, t - 0.03) / 0.06) * 0.85 + 0.15 * np.clip(t / 0.03, 0, 1)
    ton = rauschen * huelle * 0.5
    # ein paar leise Knackser, weich gemacht
    for _ in range(zufall.integers(3, 7) if ende else zufall.integers(1, 3)):
        stelle = int(zufall.uniform(0, 0.6) * n)
        laenge = int(rate * 0.004)
        if stelle + laenge < n:
            knack = np.hanning(laenge) * zufall.choice([-1, 1]) * zufall.uniform(0.3, 0.7)
            ton[stelle:stelle + laenge] += knack * huelle[stelle]
    ton = _bandpass(ton, rate, tief, hoch)
    ton *= (0.28 if ende else 0.17) / (np.max(np.abs(ton)) + 1e-9)
    blende = int(rate * 0.005)
    ton[:blende] *= np.linspace(0, 1, blende)
    ton[-blende:] *= np.linspace(1, 0, blende)
    return ton


def funk_effekt(audio, rate, stufe, toene=True):
    if not stufe or len(audio) < 10:
        return audio
    tief, hoch, uebersteuerung, rauschen = _FUNK_WERTE[stufe]
    zufall = np.random.default_rng()

    stimme = _bandpass(audio, rate, tief, hoch)
    stimme /= np.max(np.abs(stimme)) + 1e-9
    stimme = np.tanh(stimme * uebersteuerung) / np.tanh(uebersteuerung)
    stimme *= 0.9

    # Ganz leises Funkrauschen unter der Stimme. Es läuft durch und wird nicht ausgeblendet,
    # damit es nahtlos ins "kschhh" am Ende übergeht.
    grundrauschen = _bandpass(zufall.standard_normal(len(stimme)), rate, tief, hoch)
    grundrauschen /= np.max(np.abs(grundrauschen)) + 1e-9
    gesamt = stimme + grundrauschen * rauschen

    if not toene:
        return gesamt.astype(np.float32)
    # Mit Knacken am Anfang und "kschhh" am Ende (für Hörproben)
    return np.concatenate([funk_knacken(rate, stufe), gesamt,
                           funk_knacken(rate, stufe, ende=True)]).astype(np.float32)


def auf_rate(audio, rate, ziel=24000):
    """Rechnet Ton auf eine andere Abtastrate um, damit alles in einen Tonstrom passt."""
    if rate == ziel or len(audio) < 2:
        return np.asarray(audio, dtype=np.float32)
    laenge = int(round(len(audio) * ziel / rate))
    alt = np.linspace(0, 1, len(audio), endpoint=False)
    neu = np.linspace(0, 1, laenge, endpoint=False)
    return np.interp(neu, alt, audio).astype(np.float32)


class Tonstrom:
    """Ein durchgehend laufender Lautsprecher-Ausgang. Ton wird lückenlos hinten angehängt,
    so gibt es zwischen Knacken, Sätzen und Rauschen keine Pausen."""
    RATE = 24000

    def __init__(self, geraet=None):
        import sounddevice as sd
        self._stuecke = deque()
        self._position = 0
        self._rest = 0
        self._sperre = threading.Lock()
        self._strom = sd.OutputStream(samplerate=self.RATE, channels=1, dtype="float32",
                                      device=geraet, callback=self._fuellen)
        self._strom.start()

    def _fuellen(self, ausgang, anzahl, zeit, status):
        ausgang.fill(0)
        geschrieben = 0
        with self._sperre:
            while geschrieben < anzahl and self._stuecke:
                stueck = self._stuecke[0]
                n = min(anzahl - geschrieben, len(stueck) - self._position)
                ausgang[geschrieben:geschrieben + n, 0] = stueck[self._position:self._position + n]
                geschrieben += n
                self._position += n
                self._rest -= n
                if self._position >= len(stueck):
                    self._stuecke.popleft()
                    self._position = 0

    def anhaengen(self, audio):
        audio = np.asarray(audio, dtype=np.float32)
        with self._sperre:
            self._stuecke.append(audio)
            self._rest += len(audio)

    def leeren(self):
        """Sofort aufhören, mit 10 ms Ausblenden statt hartem Knacks."""
        with self._sperre:
            auslauf = None
            if self._stuecke:
                stueck = self._stuecke[0][self._position:self._position + int(self.RATE * 0.01)]
                auslauf = stueck * np.linspace(1, 0, len(stueck), dtype=np.float32)
            self._stuecke.clear()
            self._position = 0
            self._rest = 0
            if auslauf is not None and len(auslauf):
                self._stuecke.append(auslauf)
                self._rest = len(auslauf)

    def rest(self):
        """Wie viele Sekunden noch zu spielen sind."""
        return max(0, self._rest) / self.RATE

    def schliessen(self):
        try:
            self._strom.stop()
            self._strom.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 4) Sprachausgabe mit Warteschlange
# Läuft in einem eigenen Thread. Wichtigkeit: 0 = dringend, 1 = normal, 2 = nebenbei.
# ---------------------------------------------------------------------------
MAX_ALTER = {0: 6.0, 1: 20.0, 2: 10.0}   # so lange darf eine Ansage höchstens warten
SATZPAUSE = 0.4                          # Sekunden Pause zwischen zwei Sätzen eines Funkspruchs
SATZ_TRENNER = re.compile(r"(?<=[.!?])\s+(?=\S)")


def funk_pause(rate, stufe, dauer):
    """Eine Pause, in der nur das leise Funkrauschen weiterläuft."""
    anzahl = int(rate * dauer)
    if not stufe or anzahl <= 0:
        return np.zeros(max(anzahl, 0), np.float32)
    tief, hoch, _, rauschen = _FUNK_WERTE[stufe]
    hauch = _bandpass(np.random.default_rng().standard_normal(anzahl), rate, tief, hoch)
    hauch /= np.max(np.abs(hauch)) + 1e-9
    return (hauch * rauschen).astype(np.float32)


MAX_WARTEN = 8      # so lange wartet eine normale Meldung höchstens auf eine Gerade


class Sprachausgabe:
    """Spricht Funksprüche. Zwei Helfer arbeiten gleichzeitig:
       - der Erzeuger verwandelt Text in Ton (das dauert je nach Stimme etwas)
       - der Abspieler spielt fertigen Ton ab
    So wird der nächste Satz schon erzeugt, während der vorige noch läuft.
    Ein Funkspruch kann aus mehreren Sätzen bestehen (z. B. wenn die KI Satz für Satz
    antwortet). Das "ba-ding" kommt nur am Anfang, das "ding-ba" nur am Ende."""

    def __init__(self, stimme_id="", tempo=2, lautstaerke=100, funk=2, geraet=None,
                 melden=None, beim_start=None):
        self.stimme_id = stimme_id
        self.tempo = tempo
        self.lautstaerke = lautstaerke
        self.funk = funk
        self.geraet = geraet
        self.melden = melden             # meldet ans Fenster, wenn eine Ersatzstimme einspringt
        self.beim_start = beim_start     # wird aufgerufen, wenn ein Funkspruch hörbar beginnt
        self.darf_reden = None           # Funktion: True, wenn gerade geredet werden darf (Gerade)
        self.name = ""
        self.letzter_text = ""
        self._texte = []                 # wartende Sätze (dicts)
        self._toene = deque()            # fertig erzeugter Ton (dicts)
        self._sperre = threading.Lock()
        self._neuer_text = threading.Event()
        self._neuer_ton = threading.Event()
        self._abbrechen = threading.Event()
        self._generation = 0             # steigt bei jedem Abbruch, alter Ton wird verworfen
        self._zaehler = 0
        self._aktiv = True
        self._halten = False             # True, solange der Fahrer funkt
        self._spielt = False
        self._erzeugt = False
        self._offene_sprueche = {}       # spruch -> Liste der Sätze (für "Nochmal")
        self._rang = {}                  # spruch -> (wichtigkeit, zeit)
        self._erzeugt_spruch = None
        self._vorab_wunsch = False
        self._signal = None
        self._fertige_sprueche = set()   # Sprüche, zu denen kein Satz mehr kommt
        self._bereit = threading.Event()
        self._fehler = None
        aussprache_laden()               # Änderungen an aussprache.json sofort übernehmen
        threading.Thread(target=self._erzeuger, daemon=True).start()
        self._bereit.wait(timeout=180)
        if self._fehler:
            raise self._fehler
        threading.Thread(target=self._abspieler, daemon=True).start()

    # --- von außen --------------------------------------------------------
    def sagen(self, text, wichtigkeit=1, sofort=False, spruch=None, letzter=True):
        """Einen Satz sprechen. Gibt die Nummer des Funkspruchs zurück.
        sofort=True: Aktuelles abbrechen (für Antworten auf Fragen).
        spruch=...: Satz gehört zu einem schon begonnenen Funkspruch.
        letzter=False: Es kommen noch weitere Sätze (abschliessen() aufrufen)."""
        saetze = [satz for satz in SATZ_TRENNER.split(text.strip()) if satz]
        if len(saetze) > 1:
            # Jeden Satz einzeln: dann gibt es zwischen den Sätzen eine hörbare Pause
            spruch = self.sagen(saetze[0], wichtigkeit, sofort, spruch, letzter=False)
            for satz in saetze[1:-1]:
                self.sagen(satz, spruch=spruch, letzter=False)
            return self.sagen(saetze[-1], spruch=spruch, letzter=letzter)
        with self._sperre:
            if sofort:
                self._alles_abbrechen(dringende_behalten=True)
                wichtigkeit = -1
            self._zaehler += 1
            if spruch is None:
                spruch = self._zaehler
                self._offene_sprueche[spruch] = []
            # Weitere Sätze eines Spruchs erben dessen Rang, damit nichts dazwischenkommt
            if spruch not in self._rang:
                self._rang[spruch] = (wichtigkeit, time.monotonic())
            rang, zeit = self._rang[spruch]
            eintrag = {"text": text, "wichtigkeit": rang, "zeit": zeit,
                       "nr": self._zaehler, "spruch": spruch, "letzter": letzter}
            self._texte.append(eintrag)
            self._offene_sprueche.setdefault(spruch, []).append(text)
            if letzter:
                self._fertige_sprueche.add(spruch)
        self._neuer_text.set()
        return spruch

    def taste_ton(self, gedrueckt):
        """Funktaste gedrückt: 'ba-ding'. Losgelassen: 'ding-ba'. Wird sofort gespielt."""
        if self.funk:
            self._signal = "an" if gedrueckt else "aus"
            self._abbrechen.set()            # laufende Durchsage stoppen
            self._neuer_ton.set()

    def funk_oeffnen(self):
        """Sofort das 'ba-ding' spielen (z. B. direkt nach dem Loslassen der Funktaste),
        während die Antwort noch erzeugt wird. Der nächste Funkspruch beginnt dann ohne Ton."""
        self._vorab_wunsch = True
        self._neuer_ton.set()

    def abschliessen(self, spruch):
        """Zu diesem Funkspruch kommt nichts mehr."""
        with self._sperre:
            self._fertige_sprueche.add(spruch)
        self._neuer_ton.set()

    def stoppen(self):
        """Alles abbrechen und Warteschlange leeren."""
        with self._sperre:
            self._alles_abbrechen(dringende_behalten=False)

    def halten(self, an):
        """Während der Fahrer funkt, nichts abspielen."""
        self._halten = an
        if an:
            self._abbrechen.set()
        else:
            self._neuer_ton.set()

    def spricht(self):
        return (self._spielt or self._erzeugt or bool(self._texte) or bool(self._toene)
                or (hasattr(self, "_ton") and self._ton.rest() > 0))

    def beenden(self):
        self._aktiv = False
        self.stoppen()
        self._neuer_text.set()
        self._neuer_ton.set()

    def _alles_abbrechen(self, dringende_behalten):
        """Nur mit gehaltener Sperre aufrufen."""
        self._generation += 1
        if dringende_behalten:
            self._texte = [e for e in self._texte if e["wichtigkeit"] == 0]
        else:
            self._texte = []
        self._toene.clear()
        self._abbrechen.set()

    # --- Erzeuger: Text -> Ton --------------------------------------------
    def _naechster_text(self):
        with self._sperre:
            jetzt = time.monotonic()
            self._texte = [e for e in self._texte
                           if e["wichtigkeit"] < 0 or jetzt - e["zeit"] <= MAX_ALTER.get(e["wichtigkeit"], 15)]
            if not self._texte:
                return None, None
            self._texte.sort(key=lambda e: (e["wichtigkeit"], e["zeit"], e["nr"]))
            return self._texte.pop(0), self._generation

    def _erzeuger(self):
        import pythoncom
        pythoncom.CoInitialize()
        try:
            stimme = stimme_laden(self.stimme_id, self.tempo)
            self.name = stimme.name
        except Exception as fehler:
            self._fehler = fehler
            self._bereit.set()
            return
        self._bereit.set()
        ersatz = None
        neural_pause_bis = 0.0            # nach Ausfällen kurz direkt die Ersatzstimme nehmen
        ausfaelle = 0
        ersatz_sprueche = set()           # Funksprüche, die schon mit der Ersatzstimme laufen

        while self._aktiv:
            self._neuer_text.wait(timeout=0.2)
            self._neuer_text.clear()
            while self._aktiv:
                eintrag, generation = self._naechster_text()
                if eintrag is None:
                    break
                self._erzeugt = True
                self._erzeugt_spruch = eintrag["spruch"]
                try:
                    neural = getattr(stimme, "neural", False)
                    art = getattr(stimme, "art", None)
                    audio = rate = None
                    spruch = eintrag["spruch"]
                    # Ein Funkspruch bleibt in EINER Stimme: hat ein Satz schon die Ersatzstimme
                    # gebraucht, sprechen auch die restlichen Sätze dieses Spruchs mit ihr.
                    ersatz_im_spruch = spruch in ersatz_sprueche
                    if neural and not ersatz_im_spruch and time.monotonic() >= neural_pause_bis:
                        # Zwei Versuche, bevor die Ersatzstimme einspringt. Normale Meldungen
                        # dürfen länger warten als Antworten auf deine Fragen.
                        # Lieber kurz warten als mitten im Rennen die Stimme wechseln: drei Versuche.
                        versuche = getattr(stimme, "VERSUCHE", None) or (
                            (stimme.ZEITLIMIT, 4.0, 5.0) if eintrag["wichtigkeit"] < 0 else (stimme.ZEITLIMIT, 6.0, 8.0))
                        for zeitlimit in versuche:
                            try:
                                audio, rate = stimme.erzeugen(aussprechen(eintrag["text"], neural, art),
                                                              zeitlimit=zeitlimit)
                                ausfaelle = 0
                                break
                            except Exception as fehler:
                                print(f"Neural-Stimme: {type(fehler).__name__} nach {zeitlimit} s")
                        if audio is None:
                            ausfaelle += 1
                            if ausfaelle >= 3:      # dreimal hintereinander? Kurz Pause, dann wieder Neural
                                neural_pause_bis = time.monotonic() + 20
                    elif not neural:
                        audio, rate = stimme.erzeugen(aussprechen(eintrag["text"], False, art))
                    if audio is None:
                        ersatz_sprueche.add(spruch)
                        del_alte = [x for x in ersatz_sprueche if x < spruch - 50]
                        for x in del_alte:
                            ersatz_sprueche.discard(x)
                        if ersatz is None:
                            ersatz = ersatz_laden(self.tempo)
                            if self.melden:
                                self.melden(L(f"Die Neural-Stimme antwortet gerade nicht schnell genug, "
                                              f"ich nehme {ersatz.name}.",
                                              f"The neural voice isn't responding fast enough, using {ersatz.name}."))
                        audio, rate = ersatz.erzeugen(aussprechen(eintrag["text"], False))
                    audio = funk_effekt(audio, rate, self.funk, toene=False) * (self.lautstaerke / 100)
                    audio = auf_rate(audio, rate, Tonstrom.RATE)
                    with self._sperre:
                        if generation == self._generation:      # inzwischen abgebrochen?
                            self._toene.append({"audio": audio, "rate": rate, "spruch": eintrag["spruch"],
                                                "text": eintrag["text"], "wichtigkeit": eintrag["wichtigkeit"],
                                                "bereit": time.monotonic()})
                    self._neuer_ton.set()
                except Exception:
                    import traceback
                    traceback.print_exc()
                finally:
                    self._erzeugt = False
                    self._erzeugt_spruch = None
        pythoncom.CoUninitialize()

    # --- Abspieler ----------------------------------------------------------
    def _bis_fertig(self, abbrechbar=True):
        """Wartet, bis der Tonstrom alles gespielt hat. False, wenn abgebrochen wurde."""
        while self._ton.rest() > 0:
            if abbrechbar and self._abbrechen.is_set():
                self._ton.leeren()
                return False
            if not self._aktiv:
                return False
            time.sleep(0.01)
        return True

    def _spruch_fertig(self, spruch):
        """Kommt zu diesem Funkspruch noch ein Satz?"""
        with self._sperre:
            return (spruch in self._fertige_sprueche and self._erzeugt_spruch != spruch
                    and not any(e["spruch"] == spruch for e in self._texte)
                    and not any(t["spruch"] == spruch for t in self._toene))

    def _naechster_ton(self, spruch=None, warten=0.0):
        """Holt den nächsten Ton. Mit spruch: nur einen Satz dieses Funkspruchs."""
        ende = time.monotonic() + warten
        while True:
            with self._sperre:
                if self._toene and not self._halten:
                    if spruch is not None and self._toene[0]["spruch"] == spruch:
                        return self._toene.popleft()
                    if spruch is None and self._darf_jetzt(self._toene[0]):
                        return self._toene.popleft()
                    return None                         # ein anderer Spruch ist dran
                if spruch is not None and spruch in self._fertige_sprueche and not any(
                        e["spruch"] == spruch for e in self._texte) and self._erzeugt_spruch != spruch:
                    return None                         # zu diesem Spruch kommt nichts mehr
            rest = ende - time.monotonic()
            if rest <= 0 or not self._aktiv:
                return None
            self._neuer_ton.wait(timeout=min(rest, 0.05))
            self._neuer_ton.clear()

    def _darf_jetzt(self, ton):
        """Darf dieser Funkspruch jetzt beginnen? Dringendes und Antworten immer sofort.
        Normale Meldungen warten auf eine Gerade (höchstens MAX_WARTEN Sekunden)."""
        if ton.get("wichtigkeit", 1) < 1 or self.darf_reden is None:
            return True
        if time.monotonic() - ton.get("bereit", 0) > MAX_WARTEN:
            return True
        try:
            return bool(self.darf_reden())
        except Exception:
            return True

    def _abspieler(self):
        self._ton = Tonstrom(self.geraet)
        rate = Tonstrom.RATE
        laut = lambda ton: auf_rate(ton, rate, rate) * (self.lautstaerke / 100)
        try:
            while self._aktiv:
                # Funktaste gedrückt oder losgelassen: sofort "ba-ding" bzw. "ding-ba"
                if self._signal:
                    signal, self._signal = self._signal, None
                    self._ton.leeren()
                    self._abbrechen.clear()
                    self._ton.anhaengen(laut(funk_ton(rate, self.funk, ende=(signal == "aus"))))
                    continue
                self._vorab_wunsch = False
                ton = self._naechster_ton(warten=0.05)
                if ton is None:
                    continue
                self._funkspruch(ton, rate, laut)
        finally:
            self._ton.schliessen()

    def _funkspruch(self, ton, rate, laut):
        """Spielt einen ganzen Funkspruch: Knacken, alle Sätze, Rauschen. Ohne Lücken."""
        self._spielt = True
        self._abbrechen.clear()
        spruch = ton["spruch"]
        gesprochen = []
        abgebrochen = False
        try:
            if self.funk:
                self._ton.anhaengen(laut(funk_knacken(rate, self.funk)))
            if self.beim_start:
                try:
                    self.beim_start(spruch)
                except Exception:
                    pass
            while ton is not None:
                if gesprochen:                                 # ab dem zweiten Satz: Pause davor
                    self._ton.anhaengen(laut(funk_pause(rate, self.funk, SATZPAUSE)) if self.funk
                                        else np.zeros(int(rate * SATZPAUSE), np.float32))
                self._ton.anhaengen(ton["audio"])
                gesprochen.append(ton["text"])
                # Auf den nächsten Satz warten, während der aktuelle noch läuft
                ton = None
                still_seit = None
                while True:
                    if self._abbrechen.is_set() or self._signal or not self._aktiv:
                        abgebrochen = True
                        break
                    ton = self._naechster_ton(spruch=spruch, warten=0.03)
                    if ton is not None or self._spruch_fertig(spruch):
                        break
                    if self._ton.rest() == 0:              # alles gespielt, warten auf die KI
                        still_seit = still_seit or time.monotonic()
                        if time.monotonic() - still_seit > 4:
                            break
                if abgebrochen:
                    break
            if abgebrochen:
                self._ton.leeren()
            else:
                if self.funk:
                    self._ton.anhaengen(laut(funk_knacken(rate, self.funk, ende=True)))
                self._bis_fertig()
        finally:
            if gesprochen:
                self.letzter_text = " ".join(gesprochen)
            with self._sperre:
                self._offene_sprueche.pop(spruch, None)
                self._fertige_sprueche.discard(spruch)
                if not any(e["spruch"] == spruch for e in self._texte):
                    self._rang.pop(spruch, None)
            self._spielt = False
