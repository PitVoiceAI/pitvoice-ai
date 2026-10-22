# acc_app.py
# Das Programmfenster für den ACC-Renningenieur.
#   - Cockpit mit Pitboard: Platz, Abstände, Tank, Boxenstopp, Restzeit
#   - Funk-Verlauf wie ein Chat
#   - Automatische Ansagen (einzeln abschaltbar)
#   - KI-Verständnis über Ollama (versteht auch frei formulierte Fragen)
#   - Einstellungen: Stimme (Neural, Piper, Windows), Aussprache, Funk-Effekt, Tempo,
#     Lautstärke, Funktaste, Mikrofon, Erkennung, Sprit-Reserve
#
# Beim ersten Mal starten mit:  py -3.13 acc_app.py
# Danach einfach über die Desktop-Verknüpfung.

import json
import os
import queue
import random
import sys
import threading
import time
import traceback

ORDNER = os.path.dirname(os.path.abspath(__file__))
os.chdir(ORDNER)                 # damit alles gefunden wird, auch beim Start per Verknüpfung
sys.path.insert(0, ORDNER)

# Ohne schwarzes Fenster (pythonw) gibt es keine Konsole. Meldungen landen dann in einer Datei.
LOGDATEI = os.path.join(ORDNER, "renningenieur_log.txt")
if sys.stdout is None or sys.stderr is None:
    _log = open(LOGDATEI, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import tkinter as tk
from tkinter import messagebox


def _python_programm():
    """python.exe (mit Konsole) für pip, auch wenn wir selbst als pythonw laufen."""
    programm = os.path.join(os.path.dirname(sys.executable), "python.exe")
    return programm if os.path.exists(programm) else sys.executable


def _customtkinter_holen():
    """customtkinter macht die Oberfläche modern. Fehlt es, installieren wir es einmalig."""
    try:
        import customtkinter
        return customtkinter
    except ImportError:
        pass
    import importlib
    import subprocess
    hinweis = tk.Tk()
    hinweis.title(PRODUKT)
    hinweis.geometry("420x120")
    hinweis.configure(bg="#1B1E24")
    tk.Label(hinweis, text="Die neue Oberfläche wird installiert.\nDas passiert nur beim ersten Start.",
             bg="#1B1E24", fg="#ECEEF2", font=("Segoe UI", 11)).pack(expand=True)
    hinweis.update()
    ergebnis = subprocess.run([_python_programm(), "-m", "pip", "install", "customtkinter"],
                              capture_output=True, text=True,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    hinweis.destroy()
    if ergebnis.returncode != 0:
        print(ergebnis.stdout, ergebnis.stderr)
        messagebox.showerror(PRODUKT,
                             "customtkinter konnte nicht installiert werden.\n"
                             "Bitte in cmd eingeben:\npy -3.13 -m pip install customtkinter")
        sys.exit(1)
    importlib.invalidate_caches()
    import customtkinter
    return customtkinter


ctk = _customtkinter_holen()

import acc_funktaste
import acc_ki
import acc_protokoll
import acc_renningenieur as ri
import acc_sprache
from acc_sprache import L

PRODUKT = "PitVoice AI"
LIZENZ = "GPL-3.0"                # siehe LIZENZ.txt
VERSION = "1.0.0"
# Hier prüft das Programm bei jedem Start, ob es eine neue Version gibt. Leer = keine Prüfung.
# Die Datei dort ist eine kleine JSON-Datei, zum Beispiel:
#   {"version": "1.0.1", "seite": "https://pitvoice.com/#updates", "neu_de": "Was neu ist", "neu_en": "What's new"}
UPDATE_ADRESSE = "https://pitvoice.com/version.json"
# Links für "Projekt unterstützen" (leer = Knopf wird nicht angezeigt)
NEWSLETTER_ADRESSE = ""      # Anmeldeseite des Newsletter-Anbieters (z. B. Brevo, Mailchimp)
SPENDEN_ADRESSE = "https://buymeacoffee.com/pitvoiceai"   # Buy-Me-a-Coffee-Seite


def _versionsnummer(text):
    teile = []
    for teil in str(text).strip().lstrip("vV").split("."):
        ziffern = "".join(z for z in teil if z.isdigit())
        teile.append(int(ziffern) if ziffern else 0)
    return tuple(teile + [0] * (3 - len(teile)))


def update_pruefen(adresse=None, zeitlimit=5.0):
    """Gibt die Infos zur neuen Version zurück, oder None (keine neue Version oder nicht erreichbar)."""
    adresse = adresse if adresse is not None else UPDATE_ADRESSE
    if not adresse:
        return None
    import urllib.request
    try:
        anfrage = urllib.request.Request(adresse, headers={"User-Agent": f"PitVoice-AI/{VERSION}"})
        with urllib.request.urlopen(anfrage, timeout=zeitlimit) as antwort:
            daten = json.loads(antwort.read(65536).decode("utf-8"))
    except Exception:
        return None
    neu = str(daten.get("version", ""))
    if not neu or _versionsnummer(neu) <= _versionsnummer(VERSION):
        return None
    seite = str(daten.get("seite", ""))
    if not seite.startswith("https://"):
        seite = ""
    return {"version": neu, "seite": seite,
            "neu": str(daten.get("neu_en" if acc_sprache.englisch() else "neu_de", ""))[:300]}
import acc_sprit
from acc_ansagen import ANSAGEN, GESPRAECHIG_STUFEN, STANDARD_ANSAGEN, Ansagen, Geradenwaechter
from acc_renningenieur import (MEDIEN_TEXT, MEDIENTASTEN, WORTHILFE, Rennstand, beantworten,
                               medien_steuern, verstehen_mehrfach)
from acc_stimme import (AUSSPRACHE_DATEI, FUNK_STUFEN, Sprachausgabe, aussprache_laden,
                        piper_herunterladen, stimmen_liste)

EINSTELLUNGEN_DATEI = os.path.join(ORDNER, "einstellungen.json")
ABTASTRATE = 16000

STANDARD = {
    "sprache": "de",                # "de" oder "en": Oberfläche, Spracherkennung, Ansagen und KI
    "stimme": "",
    "neural_ok": False,             # Hinweis zu den inoffiziellen Neural-Stimmen bestätigt
    "tempo": 2,
    "lautstaerke": 100,
    "begruessung": True,
    "mikrofon": "",
    "modell": "small",
    "reserve_runden": 0.5,
    "funk": 2,                      # Funk-Effekt: 0 aus, 1 leicht, 2 mittel, 3 stark
    "ansagen": dict(STANDARD_ANSAGEN),
    "ki": False,                    # KI-Verständnis (geht automatisch an, wenn ein Schlüssel eingetragen wird)
    "ki_modell": "gemma3:4b",
    "ki_anbieter": "groq",          # "groq" (Standard) oder "gemini" (online, kostenlos) oder "lokal" (Ollama)
    "schluessel_gemini": "",
    "schluessel_groq": "",
    "erkennung_online": True,       # Spracherkennung über Groq (nur wenn ein Groq-Schlüssel da ist)
    "fahrer_name": "",          # so spricht dich der Ingenieur an
    "ingenieur_name": L("Fritz", "Sam"),     # so heißt dein Ingenieur
    "gespraechig": 1,               # 0 ruhig, 1 normal, 2 viel
    "thema": "kupfer",              # Farbthema der Oberfläche (siehe oberflaeche/themen.js)
    "ki_geraet": "grafikkarte",
    "gegner_ansprache": "auto",     # "auto": "der Ferrari auf Platz 5", "name": Nachname     # oder "prozessor": dann keine FPS-Einbußen, aber langsamere Antworten
}
# Namen, die zur Sprache passen (und die die Stimme gut ausspricht)
INGENIEUR_NAMEN = L(["Fritz", "Henrik", "Jonas", "Niko"], ["Sam", "Jack", "Ollie", "Harry"])

MODELLE = [
    ("tiny", L("Sehr schnell, ungenauer", "Very fast, less accurate")),
    ("base", L("Schnell", "Fast")),
    ("small", L("Ausgewogen (empfohlen)", "Balanced (recommended)")),
    ("medium", L("Sehr genau, langsamer, 1,5 GB Download", "Very accurate, slower, 1.5 GB download")),
]
RESERVEN = [0.0, 0.25, 0.5, 1.0, 1.5, 2.0]
BEFEHLE = set(MEDIENTASTEN) | {"wiederholen", "ansagen_aus", "ansagen_an"}

# ---------------------------------------------------------------------------
# Farben: Graphit wie Asphalt bei Nacht, Gelb wie ein Pitboard,
# dazu die Farben der Zeitmessung (grün = gut, lila = Bestzeit, rot = dringend)
# ---------------------------------------------------------------------------
GRAPHIT = "#1B1E24"
SEITE = "#15171C"
TAFEL = "#23272F"
TAFEL_HELL = "#2D323C"
LINIE = "#3A404C"
PITBOARD = "#0E1013"
TEXT = "#ECEEF2"
GEDAEMPFT = "#8A93A3"
GELB = "#FFC83D"
GELB_HOVER = "#FFD670"
GELB_DUNKEL = "#2E2A1C"
GRUEN = "#3DDC84"
LILA = "#B57BFF"
ROT = "#FF5A4E"
DUNKEL_TEXT = "#16181D"


# ---------------------------------------------------------------------------
# Einstellungen speichern und laden
# ---------------------------------------------------------------------------
def begruessung_text(e):
    """'Hier ist Henrik. Funk-Check, Lutz, hörst du mich?'"""
    ingenieur = e.get("ingenieur_name") or L("dein Renningenieur", "your race engineer")
    fahrer = e.get("fahrer_name") or ""
    gruss = random.choice([
        L(f"Hier ist {ingenieur}. Funk-Check{', ' + fahrer if fahrer else ''}, hörst du mich?", f"This is {ingenieur}. Radio check{', ' + fahrer if fahrer else ''}, do you read me?"),
        L(f"{('Hallo ' + fahrer + ', hier') if fahrer else 'Hier'} ist {ingenieur}. Ich bin bereit. Funk-Check.", f"{('Hello ' + fahrer + ', this') if fahrer else 'This'} is {ingenieur}. I'm ready. Radio check."),
        L(f"{ingenieur} hier, alles bereit. Viel Spaß{', ' + fahrer if fahrer else ''}!", f"{ingenieur} here, all set. Have fun{', ' + fahrer if fahrer else ''}!"),
    ])
    return gruss


def einstellungen_laden():
    daten = dict(STANDARD)
    daten["ansagen"] = dict(STANDARD_ANSAGEN)
    gespeichert_roh = {}
    try:
        with open(EINSTELLUNGEN_DATEI, encoding="utf-8") as datei:
            gespeichert = json.load(datei)
        gespeichert_roh = dict(gespeichert)
        daten["ansagen"].update(gespeichert.pop("ansagen", {}))
        daten.update(gespeichert)
    except (OSError, ValueError):
        pass
    # Windows-Stimmen gibt es nicht mehr zur Auswahl: dann die empfohlene Neural-Stimme
    if not daten["stimme"] or ":" not in daten["stimme"] or daten["stimme"].startswith("windows:"):
        from acc_stimme import STANDARD_STIMME
        daten["stimme"] = STANDARD_STIMME.get(daten.get("sprache"), STANDARD_STIMME["de"])
    # Wer die Neural-Stimme schon vorher gewählt hatte, hat sie bewusst ausgesucht
    if daten["stimme"].startswith("edge:") and "neural_ok" not in gespeichert_roh:
        daten["neural_ok"] = True
    # Neural ohne bestätigten Hinweis: frei lizenzierte Standardstimme nehmen
    if daten["stimme"].startswith("edge:") and not daten.get("neural_ok"):
        from acc_stimme import STANDARD_STIMME
        daten["stimme"] = STANDARD_STIMME.get(daten.get("sprache", "de"), STANDARD_STIMME["de"])
    # Passt die Stimme nicht zur Sprache (z. B. deutsche Piper-Stimme bei Englisch), die empfohlene nehmen
    stimme = daten["stimme"]
    nur_deutsch = (stimme.startswith(("piper:de_", "pocket:", "edge:de-DE-")) and "Multilingual" not in stimme)
    nur_englisch = stimme.startswith(("piper:en_", "edge:en-"))
    if (daten.get("sprache") == "en" and nur_deutsch) or (daten.get("sprache", "de") == "de" and nur_englisch):
        from acc_stimme import STANDARD_STIMME
        daten["stimme"] = STANDARD_STIMME[daten.get("sprache", "de")]
    return daten


def einstellungen_speichern(daten):
    with open(EINSTELLUNGEN_DATEI, "w", encoding="utf-8") as datei:
        json.dump(daten, datei, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Mikrofone
# Windows listet jedes Mikrofon mehrfach (für verschiedene Schnittstellen).
# Wir zeigen nur die Liste der Standard-Schnittstelle.
# ---------------------------------------------------------------------------
def mikrofone_auflisten():
    try:
        import sounddevice as sd
        api = sd.query_devices(kind="input")["hostapi"]
        namen = []
        for geraet in sd.query_devices():
            name = geraet["name"]
            if (geraet["max_input_channels"] > 0 and geraet["hostapi"] == api
                    and name not in namen and "Soundmapper" not in name
                    and "Primärer" not in name):
                namen.append(name)
        return namen
    except Exception:
        return []


def mikrofon_nummer(name):
    """Nummer des Mikrofons für sounddevice, None = Windows-Standard."""
    if not name:
        return None
    import sounddevice as sd
    api = sd.query_devices(kind="input")["hostapi"]
    for nummer, geraet in enumerate(sd.query_devices()):
        if geraet["name"] == name and geraet["hostapi"] == api and geraet["max_input_channels"] > 0:
            return nummer
    return None


# ---------------------------------------------------------------------------
# Programm-Symbol: eine Zielflagge im gelben Ring, ohne Zusatzpakete gezeichnet
# ---------------------------------------------------------------------------
def symbol_png(groesse=64):
    import struct
    import zlib
    mitte = (groesse - 1) / 2
    zeilen = []
    for y in range(groesse):
        zeile = bytearray([0])
        for x in range(groesse):
            abstand = ((x - mitte) ** 2 + (y - mitte) ** 2) ** 0.5
            if abstand > groesse / 2:
                zeile += bytes((0, 0, 0, 0))                 # durchsichtig
            elif abstand > groesse / 2 - groesse / 10:
                zeile += bytes((255, 200, 61, 255))          # gelber Ring
            elif (x * 6 // groesse + y * 6 // groesse) % 2:
                zeile += bytes((20, 22, 27, 255))            # schwarzes Feld
            else:
                zeile += bytes((240, 240, 240, 255))         # weißes Feld
        zeilen.append(bytes(zeile))

    def block(art, daten):
        return (struct.pack(">I", len(daten)) + art + daten
                + struct.pack(">I", zlib.crc32(art + daten) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + block(b"IHDR", struct.pack(">IIBBBBB", groesse, groesse, 8, 6, 0, 0, 0))
            + block(b"IDAT", zlib.compress(b"".join(zeilen), 9))
            + block(b"IEND", b""))


def symbol_ico_schreiben(pfad):
    import struct
    png = symbol_png(64)
    kopf = struct.pack("<HHH", 0, 1, 1)
    eintrag = struct.pack("<BBBBHHII", 64, 64, 0, 0, 1, 32, len(png), 6 + 16)
    with open(pfad, "wb") as datei:
        datei.write(kopf + eintrag + png)


SYMBOL_DATEI = os.path.join(ORDNER, "renningenieur.ico")


def desktop_verknuepfung_erstellen():
    import win32com.client
    shell = win32com.client.Dispatch("WScript.Shell")
    desktop = shell.SpecialFolders("Desktop")
    symbol_ico_schreiben(SYMBOL_DATEI)
    # pythonw.exe startet Python ohne schwarzes Konsolenfenster
    programm = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(programm):
        programm = sys.executable
    verknuepfung = shell.CreateShortCut(os.path.join(desktop, PRODUKT + ".lnk"))
    verknuepfung.TargetPath = programm
    verknuepfung.Arguments = f'"{os.path.join(ORDNER, "acc_app.py")}"'
    verknuepfung.WorkingDirectory = ORDNER
    verknuepfung.IconLocation = SYMBOL_DATEI
    verknuepfung.Description = PRODUKT
    verknuepfung.save()
    return desktop


# ---------------------------------------------------------------------------
# Hintergrund-Aufgaben: Funktaste festlegen, Piper-Stimme laden
# ---------------------------------------------------------------------------
def funktaste_lernen(nachrichten):
    try:
        ergebnis = acc_funktaste.lernen(15)
        if ergebnis:
            nachrichten.put(("lernen_fertig", ergebnis, None))
        else:
            nachrichten.put(("lernen_fertig", None, L("Keine Taste gedrückt, Zeit abgelaufen.", "No key pressed, time is up.")))
    except Exception as fehler:
        traceback.print_exc()
        nachrichten.put(("lernen_fertig", None, L(f"Fehler: {fehler}", f"Error: {fehler}")))


def paket_installieren(modul, paket, nachrichten, text):
    """Installiert ein Python-Paket per pip, falls es fehlt."""
    import importlib
    import subprocess
    try:
        importlib.import_module(modul)
        return
    except ImportError:
        pass
    nachrichten.put(("download", text))
    ergebnis = subprocess.run([_python_programm(), "-m", "pip", "install", paket],
                              capture_output=True, text=True,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if ergebnis.returncode != 0:
        print(ergebnis.stdout, ergebnis.stderr)
        raise RuntimeError(L(f"{paket} konnte nicht installiert werden. Details in renningenieur_log.txt", f"{paket} could not be installed. Details in renningenieur_log.txt"))
    importlib.invalidate_caches()


def stimme_einrichten(stimme_id, nachrichten):
    """Neural-Stimmen brauchen das Paket edge-tts, Piper-Stimmen Piper und eine Stimmdatei."""
    try:
        if stimme_id.startswith("qwen:"):
            import acc_qwen
            dauer = acc_qwen.einrichten(lambda text: nachrichten.put(("download", text)))
            nachrichten.put(("log", "system", L(f"Qwen3-Stimme ist bereit. Der Test-Satz hat {dauer:.1f} Sekunden gebraucht.", f"The Qwen3 voice is ready. The test sentence took {dauer:.1f} seconds.")))
        elif stimme_id.startswith("edge:"):
            paket_installieren("edge_tts", "edge-tts", nachrichten, L("Installiere Neural-Stimmen ...", "Installing neural voices ..."))
        elif stimme_id.startswith("pocket:"):
            paket_installieren("pocket_tts", "pocket-tts", nachrichten,
                               L("Installiere Pocket TTS (einmalig, einige hundert MB, dauert etwas) ...", "Installing Pocket TTS (one-time, a few hundred MB, takes a while) ..."))
            nachrichten.put(("download", L("Lade die Stimme herunter (einmalig) ...", "Downloading the voice (one-time) ...")))
            from acc_stimme import PocketStimme
            PocketStimme(stimme_id[len("pocket:"):], 0)      # lädt Modell und Stimme einmal
        else:
            datei_name = stimme_id[len("piper:"):]
            paket_installieren("piper", "piper-tts", nachrichten,
                               L("Installiere Piper (einmalig, ca. 1 Minute) ...", "Installing Piper (one-time, about 1 minute) ..."))
            piper_herunterladen(datei_name, lambda prozent: nachrichten.put(
                ("download", L(f"Lade Stimme herunter ... {prozent} %", f"Downloading voice ... {prozent} %"))))
        nachrichten.put(("download_fertig", stimme_id, None))
    except Exception as fehler:
        traceback.print_exc()
        nachrichten.put(("download_fertig", stimme_id, str(fehler)))


def ki_status_pruefen(modell, nachrichten, e=None):
    anbieter = (e or {}).get("ki_anbieter", "groq")
    if anbieter in ("gemini", "groq"):
        import acc_online
        ok, text = acc_online.pruefen(anbieter, (e or {}).get(f"schluessel_{anbieter}", ""))
        nachrichten.put(("ki_status", L(f"Bereit: {text}", f"Ready: {text}") if ok else text, "gruen" if ok else "rot"))
        return
    modelle = acc_ki.installierte_modelle()
    if modelle is None:
        nachrichten.put(("ki_status", L("Ollama läuft nicht. Erst installieren bzw. starten.", "Ollama is not running. Install or start it first."), "rot"))
    elif not acc_ki.modell_vorhanden(modell, modelle):
        nachrichten.put(("ki_status", L('Ollama läuft. Das Modell muss noch geladen werden.', 'Ollama is running. The model still needs to be downloaded.'), "gelb"))
    else:
        nachrichten.put(("ki_status", L("Bereit", "Ready"), "gruen"))


def ki_modell_laden(modell, nachrichten):
    try:
        if acc_ki.installierte_modelle() is None:
            raise RuntimeError(L("Ollama läuft nicht. Bitte erst installieren und starten.", "Ollama is not running. Please install and start it first."))
        acc_ki.modell_laden(modell, lambda prozent: nachrichten.put(
            ("ki_status", L(f"Lade Modell ... {prozent} %", f"Downloading model ... {prozent} %"), "gelb")))
        nachrichten.put(("ki_fertig", None))
    except Exception as fehler:
        traceback.print_exc()
        nachrichten.put(("ki_fertig", str(fehler)))


def sprachausgabe_erstellen(e, nachrichten=None, beim_start=None):
    """Stimme laden. Klappt die gewählte nicht, nehmen wir die Windows-Standardstimme."""
    melden = (lambda text: nachrichten.put(("log", "fehler", text))) if nachrichten else None
    try:
        return Sprachausgabe(e["stimme"], e["tempo"], e["lautstaerke"], e["funk"], melden=melden,
                             beim_start=beim_start), None
    except Exception as fehler:
        traceback.print_exc()
        ersatz = Sprachausgabe("", e["tempo"], e["lautstaerke"], e["funk"], melden=melden,
                               beim_start=beim_start)
        return ersatz, L(f"Gewählte Stimme ging nicht ({fehler}), nehme Windows-Stimme.", f"The selected voice didn't work ({fehler}), using the backup voice.")


# ---------------------------------------------------------------------------
# Der Renningenieur im Hintergrund
# Er schickt alles, was das Fenster anzeigen soll, als Nachricht in eine
# Warteschlange (queue). Das Fenster holt sie regelmäßig ab.
# ---------------------------------------------------------------------------
class StartFehler(Exception):
    """Ein Problem, das der Nutzer selbst beheben kann."""


_modell_speicher = {}     # Spracherkennung bleibt geladen, auch nach Stopp


def zeit_kurz(ms):
    if not ri.gueltige_zeit(ms):
        return "–"
    return f"{ms // 60000}:{(ms % 60000) / 1000:04.1f}".replace(".", L(",", "."))


def abstand_anzeige(art, wert):
    if art is None or wert is None:
        return "…"
    if art == "runden":
        return f"{'+' if wert > 0 else '−'}{abs(wert)} {L('R', 'L')}"
    return f"{'+' if wert >= 0 else '−'}{abs(wert):.1f}".replace(".", L(",", "."))


class Ingenieur:
    def __init__(self, nachrichten, einstellungen):
        self.nachrichten = nachrichten
        self.e = dict(einstellungen)
        self.stopp = threading.Event()
        self.ki_modell = None
        self.stand = None
        self.gespraech = acc_ki.Gespraech()
        self._zeiten = {}                # Funkspruch -> gemessene Zeiten

    def starten(self):
        threading.Thread(target=self._lauf, daemon=True).start()

    def anhalten(self):
        self.stopp.set()

    def _melden(self, *nachricht):
        self.nachrichten.put(nachricht)

    def _lauf(self):
        stand = sprecher = None
        try:
            self._melden("status", "laedt", L("Starte ...", "Starting ..."))
            import numpy as np
            import sounddevice as sd

            acc_sprit.RESERVE_RUNDEN = float(self.e["reserve_runden"])
            acc_ki.AUF_PROZESSOR = self.e.get("ki_geraet") == "prozessor"
            ri.NAMEN_MODUS = self.e.get("gegner_ansprache", "auto")
            try:
                funktaste = acc_funktaste.Funktaste()
            except LookupError as fehler:
                raise StartFehler(str(fehler))

            self._melden("status", "laedt", L("Lade Stimme ...", "Loading voice ..."))
            sprecher, warnung = sprachausgabe_erstellen(self.e, self.nachrichten, self._ton_beginnt)
            if warnung:
                self._melden("log", "fehler", warnung)
            mikrofon = mikrofon_nummer(self.e["mikrofon"])

            self.erkennung_online = bool(self.e.get("erkennung_online") and self.e.get("schluessel_groq"))
            if not self.erkennung_online:
                self._melden("status", "laedt", L("Lade Spracherkennung ...", "Loading speech recognition ..."))
                self._lokale_erkennung()

            anbieter = self.e.get("ki_anbieter", "groq")
            acc_ki.ANBIETER = anbieter
            acc_ki.SCHLUESSEL = self.e.get(f"schluessel_{anbieter}", "")
            acc_ki.AUSWEICH = [(andere, self.e.get(f"schluessel_{andere}", "")) for andere in ("groq", "gemini")
                               if andere != anbieter and self.e.get(f"schluessel_{andere}")]
            acc_ki.MELDEN = lambda text: self._melden("log", "system", text)
            if self.e.get("ki") and anbieter in ("gemini", "groq"):
                import acc_online
                try:
                    genommen = anbieter
                    try:
                        self.ki_modell = acc_online.modell_waehlen(anbieter, acc_ki.SCHLUESSEL)
                    except acc_online.OnlineFehler:
                        if not acc_ki.AUSWEICH:
                            raise
                        genommen = acc_ki.AUSWEICH[0][0]
                        self.ki_modell = acc_online.modell_waehlen(*acc_ki.AUSWEICH[0])
                    ausweich = L(f", Ausweich: {acc_online.ANBIETER[acc_ki.AUSWEICH[0][0]]['name']}", f", backup: {acc_online.ANBIETER[acc_ki.AUSWEICH[0][0]]['name']}") if acc_ki.AUSWEICH else ""
                    self._melden("log", "system", L(f"KI online bereit ({acc_online.ANBIETER[genommen]['name']}, "
                                                  f"{self.ki_modell}{ausweich})", f"AI online ready ({acc_online.ANBIETER[genommen]['name']}, "
                                                  f"{self.ki_modell}{ausweich})"))
                except Exception as fehler:
                    self._melden("log", "fehler", L(f"KI online nicht erreichbar: {fehler}. Es geht ohne KI weiter.", f"AI online not reachable: {fehler}. Continuing without AI."))
            elif self.e.get("ki"):
                modelle = acc_ki.installierte_modelle()
                if modelle is None:
                    self._melden("log", "fehler", L("KI ist an, aber Ollama läuft nicht. Es geht ohne KI weiter.", "AI is on, but Ollama is not running. Continuing without AI."))
                elif not acc_ki.modell_vorhanden(self.e["ki_modell"], modelle):
                    self._melden("log", "fehler", L("Das KI-Modell ist noch nicht geladen (Einstellungen).", "The AI model hasn't been downloaded yet (settings)."))
                else:
                    self.ki_modell = self.e["ki_modell"]
                    threading.Thread(target=self._ki_aufwaermen, daemon=True).start()

            acc_ki.FAHRER_NAME = self.e.get("fahrer_name", "")
            ri.FAHRER_NAME = self.e.get("fahrer_name", "")
            acc_ki.INGENIEUR_NAME = self.e.get("ingenieur_name", "")
            ansagen = Ansagen(self.e["ansagen"], fahrer=self.e.get("fahrer_name", ""),
                              gespraechig=int(self.e.get("gespraechig", 1)))
            if self.ki_modell:
                def rede(fakten):
                    text = acc_ki.debrief_rede(self.ki_modell, fakten)
                    self.gespraech.merken(L("Wie war die Session?", "How was the session?"), text)
                    return text
                ansagen.rede_ki = rede
            stand = Rennstand()
            self.stand = stand
            stand.starten()
            if self.e["ansagen"].get("nur_geraden", True):
                sprecher.darf_reden = Geradenwaechter(stand)
            self._melden("status", "bereit", L("Bereit", "Ready"))
            self._melden("log", "system", L(f"Ingenieur bereit, Stimme: {sprecher.name}", f"Engineer ready, voice: {sprecher.name}"))
            if self.e["begruessung"]:
                sprecher.sagen(begruessung_text(self.e), 1)

            naechste_pruefung = 0.0
            protokoll_kennung = None
            feld_zaehler = 0
            while not self.stopp.is_set():
                if time.monotonic() >= naechste_pruefung:
                    naechste_pruefung = time.monotonic() + 0.5
                    self._melden("info", self._live_daten(stand))
                    feld_zaehler += 1
                    self._melden("feld", self._feld_daten(stand))
                    with stand.sperre:
                        meldungen = ansagen.pruefen(stand)
                        kennung = (stand.protokoll.beginn, len(stand.protokoll.runden),
                                   stand.protokoll.endplatz, stand.protokoll.startplatz)
                        if kennung != protokoll_kennung and stand.protokoll.runden:
                            protokoll_kennung = kennung
                            self._melden("protokoll", stand.protokoll.zusammenfassung())
                    for dringend, text in meldungen:
                        sprecher.sagen(text, 0 if dringend else 1)
                        self._melden("log", "ansage", text)

                if not funktaste.gedrueckt():
                    time.sleep(0.02)
                    continue

                sprecher.halten(True)            # nicht reinreden, wenn du funkst
                sprecher.taste_ton(True)         # "ba-ding"
                self._melden("funk", True)
                audio = self._aufnehmen(sd, np, funktaste.gedrueckt, mikrofon)
                losgelassen = time.monotonic()
                sprecher.taste_ton(False)        # "ding-ba"
                self._melden("funk", False)
                text = ""
                try:
                    if len(audio) / ABTASTRATE < 0.5 or self.stopp.is_set():
                        continue
                    sprecher.halten(False)
                    text = self._erkennen(audio)
                finally:
                    sprecher.halten(False)
                erkannt = time.monotonic()
                if not text:
                    self._melden("log", "system", L("Nicht verstanden", "Not understood"))
                    sprecher.sagen(L("Sag nochmal, nicht verstanden.", "Say again, didn't understand."), sofort=True)
                    continue
                self._melden("log", "du", text)
                self._befehl(text, stand, sprecher, ansagen,
                             {"los": losgelassen, "erkennung": erkannt - losgelassen})

        except StartFehler as fehler:
            self._melden("fehler", str(fehler))
        except Exception as fehler:
            traceback.print_exc()
            self._melden("fehler", L(f"Unerwarteter Fehler: {fehler}", f"Unexpected error: {fehler}"))
        finally:
            if stand:
                # Session speichern, auch wenn du vor der Zielflagge aufhörst
                try:
                    with stand.sperre:
                        if not stand.protokoll.gespeichert and len(stand.protokoll.runden) >= 2:
                            stand.protokoll.telemetrie = stand.telemetrie.export(stand.acc.streckenlaenge_m)
                            stand.protokoll.karte = acc_protokoll.karte_von(stand.acc)
                            stand.protokoll.speichern()
                except Exception:
                    traceback.print_exc()
                stand.stoppen()
            if sprecher:
                sprecher.beenden()
            self._melden("status", "aus", L("Gestoppt", "Stopped"))

    def _lokale_erkennung(self):
        """Lädt die Spracherkennung auf dem eigenen PC (einmal pro Programmstart)."""
        modell = self.e["modell"]
        if modell not in _modell_speicher:
            from faster_whisper import WhisperModel
            _modell_speicher.clear()
            _modell_speicher[modell] = WhisperModel(modell, device="cpu", compute_type="int8", cpu_threads=8)
        return _modell_speicher[modell]

    def _erkennen(self, audio):
        """Aufnahme -> Text. Online über Groq (falls eingestellt), sonst oder bei Problemen lokal."""
        if self.erkennung_online:
            try:
                import acc_online
                return acc_online.erkennen(self.e.get("schluessel_groq", ""), audio, ABTASTRATE, WORTHILFE)
            except Exception as fehler:
                self._melden("log", "system", L(f"Online-Spracherkennung ging nicht ({fehler}), nehme die lokale.", f"Online speech recognition failed ({fehler}), using the local one."))
        erkennung = self._lokale_erkennung()
        # Schnell-Einstellungen: kein Zeitstempel, kein Wiederholen bei Unsicherheit
        abschnitte, _ = erkennung.transcribe(
            audio, language=acc_sprache.SPRACHE, beam_size=1, initial_prompt=WORTHILFE,
            without_timestamps=True, condition_on_previous_text=False,
            vad_filter=False, temperature=0.0)
        return " ".join(a.text for a in abschnitte).strip()

    def _ki_aufwaermen(self):
        try:
            acc_ki.aufwaermen(self.ki_modell)
        except Exception:
            traceback.print_exc()

    def _ton_beginnt(self, spruch):
        """Wird aufgerufen, sobald eine Antwort hörbar beginnt: Zeiten anzeigen."""
        zeiten = self._zeiten.pop(spruch, None)
        if not zeiten:
            return
        gesamt = time.monotonic() - zeiten["los"]
        teile = [L(f"Erkennung {zeiten['erkennung']:.1f} s", f"recognition {zeiten['erkennung']:.1f} s")]
        rest = gesamt - zeiten["erkennung"]
        if "ki" in zeiten:
            teile.append(L(f"KI {zeiten['ki']:.1f} s", f"AI {zeiten['ki']:.1f} s"))
            rest -= zeiten["ki"]
        teile.append(L(f"Stimme {max(0.0, rest):.1f} s", f"voice {max(0.0, rest):.1f} s"))
        zeit_text = (L(f"Antwort nach {gesamt:.1f} s: ", f"Answer after {gesamt:.1f} s: ") + ", ".join(teile))
        self._melden("log", "zeit", L(zeit_text.replace(".", ","), zeit_text))

    def _befehl(self, text, stand, sprecher, ansagen, zeiten):
        """Führt aus, was der Fahrer gesagt hat (auch mehrere Dinge auf einmal)."""
        teile = verstehen_mehrfach(text)
        befehle = [t for t in teile if t[0] in BEFEHLE]
        fragen = [t for t in teile if t[0] not in BEFEHLE]

        rueckmeldungen = []
        for absicht, _ in befehle:
            if absicht in MEDIENTASTEN:
                medien_steuern(absicht)
                self._melden("log", "system", MEDIEN_TEXT[absicht])
            elif absicht == "wiederholen":
                rueckmeldungen.append(sprecher.letzter_text or L("Ich habe noch nichts gesagt.", "I haven't said anything yet."))
            elif absicht == "ansagen_aus":
                ansagen.stumm = True
                rueckmeldungen.append(L("Copy, Funkstille. Ich melde mich nur noch, wenn es dringend ist.", "Copy, radio silence. I'll only call you if it's urgent."))
            elif absicht == "ansagen_an":
                ansagen.stumm = False
                rueckmeldungen.append(L("Copy, ich halte dich wieder auf dem Laufenden.", "Copy, I'll keep you updated again."))
        if not fragen:                           # nur Befehle, keine Frage
            if rueckmeldungen:
                antwort = " ".join(rueckmeldungen)
                self._melden("log", "ingenieur", antwort)
                self._zeiten[sprecher.sagen(antwort, sofort=True)] = zeiten
            return

        spruch = None
        if rueckmeldungen:
            spruch = sprecher.sagen(" ".join(rueckmeldungen), sofort=True, letzter=False)
            self._zeiten[spruch] = zeiten

        # Mit KI: Die KI versteht die Frage selbst und bekommt alle Daten. Dazu bekommt sie,
        # was das Programm zu den erkannten Stichwörtern schon ausgerechnet hat (PASSENDE FAKTEN).
        if self.ki_modell:
            saetze = []
            beginn = time.monotonic()
            self._melden("denkt", True)
            # Braucht die KI länger als gut eine Sekunde, sagt der Ingenieur schon mal etwas,
            # statt stumm zu bleiben ("Ja Lutz, ich schau kurz nach.")
            erster_satz = threading.Event()
            sperre = threading.Lock()
            fuell = {"spruch": None}

            def fuellsatz():
                if erster_satz.wait(1.2) or spruch is not None:
                    return
                with sperre:
                    if not erster_satz.is_set():
                        fuell["spruch"] = sprecher.sagen(self._fuellsatz(), sofort=True, letzter=False)
                        self._zeiten[fuell["spruch"]] = zeiten

            threading.Thread(target=fuellsatz, daemon=True).start()
            try:
                with stand.sperre:
                    daten = acc_ki.telemetrie_text(stand)
                    fakten = []
                    if stand.acc_laeuft():
                        for absicht, zusatz in fragen:
                            if absicht not in ("unbekannt", "rat", "hilfe", "danke"):
                                try:
                                    fakten.append(beantworten(stand, absicht, zusatz))
                                except Exception:
                                    pass
                for satz in acc_ki.antworten(self.ki_modell, text, daten, self.gespraech,
                                             fakten="\n".join(fakten)):
                    with sperre:
                        erster_satz.set()
                        if spruch is None and fuell["spruch"] is not None:
                            spruch = fuell["spruch"]
                        if spruch is None:
                            zeiten["ki"] = time.monotonic() - beginn
                            spruch = sprecher.sagen(satz, sofort=True, letzter=False)
                            self._zeiten[spruch] = zeiten
                        else:
                            zeiten.setdefault("ki", time.monotonic() - beginn)
                            sprecher.sagen(satz, spruch=spruch, letzter=False)
                    saetze.append(satz)
            except Exception as fehler:
                traceback.print_exc()
                ri.KI_GESTOERT = True
                grund = f" ({fehler})" if fehler.__class__.__name__ == "OnlineFehler" else ""
                self._melden("log", "system", L(f"Die KI hat nicht geantwortet{grund}, ich antworte ohne KI", f"The AI didn't answer{grund}, answering without AI"))
            finally:
                with sperre:
                    erster_satz.set()
                    if spruch is None and fuell["spruch"] is not None:
                        spruch = fuell["spruch"]
                self._melden("denkt", False)
            if saetze:
                ri.KI_GESTOERT = False
                sprecher.abschliessen(spruch)
                self._melden("log", "ingenieur", " ".join(rueckmeldungen + saetze))
                return

        # Ohne KI (oder wenn sie nicht antwortet): Stichwörter
        antworten = []
        with stand.sperre:
            for absicht, zusatz in fragen:
                if absicht != "unbekannt":
                    antworten.append(beantworten(stand, absicht, zusatz))
        if not antworten:
            antworten = [L("Das habe ich nicht verstanden.", "I didn't understand that.")]
        antwort = " ".join(antworten)
        self.gespraech.merken(text, antwort)         # damit die KI bei Nachfragen weiß, worum es ging
        self._melden("log", "ingenieur", " ".join(rueckmeldungen + antworten))
        if spruch is None:
            self._zeiten[sprecher.sagen(antwort, sofort=True)] = zeiten
        else:
            sprecher.sagen(antwort, spruch=spruch)
            sprecher.abschliessen(spruch)

    FUELLSAETZE = L(["Ja{name}, ich schau kurz nach.", "Moment, ich prüfe das eben.", "Lass mich kurz nachschauen.",
                   "Einen Moment{name}, ich rechne das kurz durch.", "Copy, ich check das schnell.",
                   "Gute Frage, ich schau mir die Daten an.", "Sekunde, ich hab's gleich."], [
        "Yes{name}, let me check.", "One moment, checking that now.", "Let me have a quick look.",
        "One second{name}, I'm working it out.", "Copy, checking quickly.",
        "Good question, I'm looking at the data.", "Second, I'll have it in a moment."])

    def _fuellsatz(self):
        name = self.e.get("fahrer_name") or ""
        auswahl = [t for t in self.FUELLSAETZE if t != getattr(self, "_letzter_fuellsatz", None)]
        satz = random.choice(auswahl)
        self._letzter_fuellsatz = satz
        return satz.format(name=f" {name}" if name and satz.startswith(("Ja", "Yes")) else (f", {name}" if name else ""))

    def _aufnehmen(self, sd, np, gedrueckt, mikrofon):
        teile = []
        with sd.InputStream(device=mikrofon, samplerate=ABTASTRATE, channels=1, dtype="float32") as strom:
            while gedrueckt() and not self.stopp.is_set():
                daten, _ = strom.read(ABTASTRATE // 20)
                teile.append(daten[:, 0].copy())
            nachlauf, _ = strom.read(int(ABTASTRATE * 0.15))
            teile.append(nachlauf[:, 0].copy())
        return np.concatenate(teile)

    @staticmethod
    def _feld_daten(stand):
        """Karte und Rangliste für die Live-Seite."""
        with stand.sperre:
            acc = stand.acc
            d = {"autos": [], "karte": []}
            if acc.verbindungs_id is None:
                return d
            punkte = acc.streckenbild
            if len(punkte) > 40:
                d["karte"] = [(punkte[f][0], punkte[f][1]) for f in sorted(punkte)]
            ich = acc.ich()
            for platz, auto in enumerate(acc.rangliste(), start=1):
                if auto is ich:
                    abstand = ""
                else:
                    abstand = abstand_anzeige(*acc.abstand_zu(auto))
                d["autos"].append({
                    "index": auto.index, "platz": platz, "nummer": auto.nummer,
                    "name": ri.anzeige_name(auto), "fahrer": auto.fahrer, "ich": auto is ich,
                    "marke": ri.MARKEN.get(auto.modell, ""),
                    "x": auto.x, "y": auto.y, "box": auto.ort in (2, 3, 4),
                    "abstand": abstand, "letzte": auto.letzte_runde, "beste": auto.beste_runde,
                    "beste_sektoren": list(auto.beste_sektoren), "stopps": auto.boxenstopps,
                    "runden": [dict(r) for r in auto.runden_historie[-40:]],
                })
            return d

    @staticmethod
    def _live_daten(stand):
        """Alles, was das Cockpit anzeigt, als Wörterbuch."""
        with stand.sperre:
            d = {"acc": stand.acc_laeuft(), "zeitnahme": stand.acc.verbindungs_id is not None}
            if not d["acc"]:
                return d
            g, p, s = stand.grafik, stand.physik, stand.statisch
            acc = stand.acc
            d["session"] = {0: L("Training", "Practice"), 1: L("Qualifying", "Qualifying"), 2: L("Rennen", "Race")}.get(g.session, "Session")
            d["strecke"] = str(s.strecke).replace("_", " ").title()
            platz = acc.mein_platz() or (g.position or None)
            d["platz"] = platz
            d["gesamt"] = len(acc.rangliste()) or None

            def nachbar(pl):
                auto = acc.auto_auf_platz(pl) if pl and pl >= 1 else None
                if auto is None or auto is acc.ich():
                    return None
                return pl, ri.anzeige_name(auto), abstand_anzeige(*acc.abstand_zu(auto))

            d["vorne"] = nachbar(platz - 1) if platz and platz > 1 else None
            d["hinten"] = nachbar(platz + 1) if platz else None
            for richtung in ("vorne", "hinten"):
                auto, sekunden, runden = ri.strecken_nachbar(stand, richtung)
                if auto is not None:
                    d["strecke_" + richtung] = (ri.anzeige_name(auto),
                                                f"{sekunden:.1f} s".replace(".", L(",", ".")) if sekunden is not None
                                                else "…", runden)
            d["runde"] = g.runden_fertig + 1
            d["runden_gesamt"] = g.runden_gesamt
            d["letzte"] = zeit_kurz(g.i_letzte_zeit)
            d["beste"] = zeit_kurz(g.i_beste_zeit)
            d["tank"] = p.tank
            d["tank_max"] = s.tank_max or 120
            lage = ri.sprit_lage(stand)
            if lage:
                _, restrunden, e = lage
                d["reicht"] = e["reicht_runden"]
                if restrunden is not None:
                    if e["stopps"] == 0:
                        d["box"] = L("Kein Stopp nötig", "No stop needed")
                        d["box_detail"] = L(f"{e['ueberschuss']:.0f} L Reserve im Ziel", f"{e['ueberschuss']:.0f} L reserve at the finish")
                    elif e["stopps"] == 1:
                        d["box"] = L(f"{e['menge_pro_stopp']} L nachtanken", f"refuel {e['menge_pro_stopp']} L")
                        d["box_detail"] = L(f"Fenster Runde {e['fenster_von']} bis {e['fenster_bis']}", f"window lap {e['fenster_von']} to {e['fenster_bis']}")
                    else:
                        d["box"] = L(f"{e['stopps']} Stopps", f"{e['stopps']} stops")
                        d["box_detail"] = L(f"je {e['menge_pro_stopp']} L, erster bis Runde {e['fenster_bis']}", f"{e['menge_pro_stopp']} L each, first by lap {e['fenster_bis']}")
                    d["rest_runden"] = restrunden
            if g.runden_gesamt > 0:
                d["rest"] = L(f"{max(0, g.runden_gesamt - g.runden_fertig)} Runden", f"{max(0, g.runden_gesamt - g.runden_fertig)} laps")
            elif g.session_rest > 0:
                sek = int(g.session_rest / 1000)
                d["rest"] = f"{sek // 3600}:{sek % 3600 // 60:02d}:{sek % 60:02d}" if sek >= 3600 \
                    else f"{sek // 60}:{sek % 60:02d}"
            else:
                d["rest"] = L("Letzte Runde", "Last lap")
            return d


# ---------------------------------------------------------------------------
# Kleine Bausteine für das Fenster
# ---------------------------------------------------------------------------
SCHRIFT = "Segoe UI"
SCHRIFT_ENG = "Segoe UI"


def zeit_anzeige(ms):
    """138512 -> '2:18,512'"""
    if not ms or ms <= 0:
        return "–"
    minuten, rest = divmod(ms / 1000, 60)
    return f"{int(minuten)}:{rest:06.3f}".replace(".", L(",", "."))


def schrift(groesse, fett=False, eng=False):
    return ctk.CTkFont(family=SCHRIFT_ENG if eng else SCHRIFT, size=groesse,
                       weight="bold" if fett else "normal")


class Auswahl(ctk.CTkFrame):
    """Eine Reihe Knöpfe, von denen einer gewählt ist (z. B. Funk-Effekt)."""

    def __init__(self, eltern, werte, aktuell, befehl):
        super().__init__(eltern, fg_color="transparent")
        self.befehl = befehl
        self.knoepfe = {}
        for i, wert in enumerate(werte):
            knopf = ctk.CTkButton(self, text=wert, width=74, height=32, corner_radius=8,
                                  font=schrift(13), command=lambda w=wert: self.waehlen(w, True))
            knopf.grid(row=0, column=i, padx=(0 if i == 0 else 4, 0))
            self.knoepfe[wert] = knopf
        self.waehlen(aktuell, False)

    def waehlen(self, wert, melden):
        self.wert = wert
        for w, knopf in self.knoepfe.items():
            if w == wert:
                knopf.configure(fg_color=GELB, hover_color=GELB_HOVER, text_color=DUNKEL_TEXT)
            else:
                knopf.configure(fg_color=TAFEL_HELL, hover_color=LINIE, text_color=TEXT)
        if melden:
            self.befehl(wert)

    def get(self):
        return self.wert


def auswahlmenue(eltern, variable, werte, befehl, breite=380):
    return ctk.CTkOptionMenu(eltern, variable=variable, values=werte, command=befehl, width=breite,
                             height=34, corner_radius=8, fg_color=TAFEL_HELL, button_color=TAFEL_HELL,
                             button_hover_color=LINIE, text_color=TEXT, font=schrift(13),
                             dropdown_fg_color=TAFEL, dropdown_hover_color=TAFEL_HELL,
                             dropdown_text_color=TEXT, dropdown_font=schrift(13),
                             dynamic_resizing=False)


def nebenknopf(eltern, text, befehl, breite=100):
    return ctk.CTkButton(eltern, text=text, command=befehl, width=breite, height=34, corner_radius=8,
                         fg_color=TAFEL_HELL, hover_color=LINIE, text_color=TEXT, font=schrift(13))


# ---------------------------------------------------------------------------
# Das Fenster
# ---------------------------------------------------------------------------
SEITEN = [("cockpit", "Cockpit"), ("live", "Live-Karte"), ("funk", "Funk"), ("auswertung", "Auswertung"), ("ansagen", "Ansagen"),
          ("einstellungen", "Einstellungen"), ("befehle", "Befehle")]


class App:
    def __init__(self, root):
        self.root = root
        self.e = einstellungen_laden()
        self.nachrichten = queue.Queue()
        self.ingenieur = None
        self.zustand = "aus"          # aus, laedt, bereit, stoppt
        self.test_sprecher = None
        self.lernt = False
        self._speicher_timer = None
        self.funk_zeilen = []
        self.aktuelle_seite = None

        root.title(PRODUKT)
        root.geometry("1120x740")
        root.minsize(980, 660)
        root.configure(fg_color=GRAPHIT)
        try:
            symbol_ico_schreiben(SYMBOL_DATEI)
            root.iconbitmap(SYMBOL_DATEI)
        except Exception:
            pass

        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(0, weight=1)
        self._seitenleiste()
        self.inhalt = ctk.CTkFrame(root, fg_color=GRAPHIT, corner_radius=0)
        self.inhalt.grid(row=0, column=1, sticky="nsew")
        self.inhalt.grid_columnconfigure(0, weight=1)
        self.inhalt.grid_rowconfigure(0, weight=1)

        self.seiten = {
            "cockpit": self._seite_cockpit(),
            "live": self._seite_live(),
            "funk": self._seite_funk(),
            "auswertung": self._seite_auswertung(),
            "ansagen": self._seite_ansagen(),
            "einstellungen": self._seite_einstellungen(),
            "befehle": self._seite_befehle(),
        }
        self.zeigen("cockpit")
        self._cockpit_leer("Starte den Ingenieur unten links.")
        self._funk_eintrag("system", "Drück auf Starten. Dann Funktaste halten und sprechen.")
        root.protocol("WM_DELETE_WINDOW", self._schliessen)
        root.after(100, self._nachrichten_abholen)
        root.after(500, self._ki_pruefen)

    # --- Seitenleiste ------------------------------------------------------
    def _seitenleiste(self):
        leiste = ctk.CTkFrame(self.root, fg_color=SEITE, corner_radius=0, width=230)
        leiste.grid(row=0, column=0, sticky="nsw")
        leiste.grid_propagate(False)
        leiste.grid_columnconfigure(0, weight=1)
        leiste.grid_rowconfigure(2, weight=1)

        marke = ctk.CTkFrame(leiste, fg_color="transparent")
        marke.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 28))
        zeichen = ctk.CTkLabel(marke, text="R", width=38, height=38, corner_radius=8,
                               fg_color=GELB, text_color=DUNKEL_TEXT, font=schrift(22, True, True))
        zeichen.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ctk.CTkLabel(marke, text=PRODUKT, text_color=TEXT, font=schrift(18, True),
                     anchor="w").grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(marke, text="Assetto Corsa Competizione", text_color=GEDAEMPFT,
                     font=schrift(11), anchor="w").grid(row=1, column=1, sticky="w")

        navigation = ctk.CTkFrame(leiste, fg_color="transparent")
        navigation.grid(row=1, column=0, sticky="ew", padx=12)
        navigation.grid_columnconfigure(1, weight=1)
        self.nav = {}
        for i, (schluessel, text) in enumerate(SEITEN):
            strich = ctk.CTkFrame(navigation, width=4, height=26, corner_radius=2, fg_color=SEITE)
            strich.grid(row=i, column=0, padx=(0, 6), pady=3)
            knopf = ctk.CTkButton(navigation, text=text, anchor="w", height=40, corner_radius=8,
                                  fg_color="transparent", hover_color=TAFEL, text_color=GEDAEMPFT,
                                  font=schrift(15), command=lambda s=schluessel: self.zeigen(s))
            knopf.grid(row=i, column=1, sticky="ew", pady=3)
            self.nav[schluessel] = (knopf, strich)

        unten = ctk.CTkFrame(leiste, fg_color="transparent")
        unten.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 22))
        unten.grid_columnconfigure(1, weight=1)
        self.funk_anzeige = ctk.CTkLabel(unten, text="", text_color=ROT, font=schrift(13, True),
                                         anchor="w")
        self.funk_anzeige.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.punkt = ctk.CTkLabel(unten, text="●", text_color=GEDAEMPFT, font=schrift(14), width=16)
        self.punkt.grid(row=1, column=0, sticky="w")
        self.status_text = ctk.CTkLabel(unten, text="Gestoppt", text_color=GEDAEMPFT,
                                        font=schrift(13), anchor="w")
        self.status_text.grid(row=1, column=1, sticky="w", padx=(6, 0))
        self.start_knopf = ctk.CTkButton(unten, text="Starten", height=52, corner_radius=10,
                                         fg_color=GELB, hover_color=GELB_HOVER, text_color=DUNKEL_TEXT,
                                         font=schrift(17, True), command=self._start_stopp)
        self.start_knopf.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def zeigen(self, schluessel):
        self.aktuelle_seite = schluessel
        if schluessel == "live":
            self.root.after(20, self._live_zeigen)
        for name, seite in self.seiten.items():
            if name == schluessel:
                seite.grid(row=0, column=0, sticky="nsew")
            else:
                seite.grid_forget()
        for name, (knopf, strich) in self.nav.items():
            aktiv = name == schluessel
            knopf.configure(fg_color=TAFEL if aktiv else "transparent",
                            text_color=TEXT if aktiv else GEDAEMPFT)
            strich.configure(fg_color=GELB if aktiv else SEITE)
        if schluessel == "funk":
            self.root.after(50, self._funk_nach_unten)
        if schluessel == "auswertung":
            self._auswertung_liste()

    def _seitenkopf(self, eltern, titel, untertitel):
        kopf = ctk.CTkFrame(eltern, fg_color="transparent")
        kopf.grid(row=0, column=0, columnspan=2, sticky="ew", padx=32, pady=(26, 18))
        ctk.CTkLabel(kopf, text=titel, text_color=TEXT, font=schrift(28, True), anchor="w"
                     ).grid(row=0, column=0, sticky="w")
        unter = ctk.CTkLabel(kopf, text=untertitel, text_color=GEDAEMPFT, font=schrift(13), anchor="w")
        unter.grid(row=1, column=0, sticky="w")
        return unter

    # --- Cockpit -----------------------------------------------------------
    def _seite_cockpit(self):
        seite = ctk.CTkFrame(self.inhalt, fg_color="transparent")
        seite.grid_columnconfigure(0, weight=3)
        seite.grid_columnconfigure(1, weight=2)
        seite.grid_rowconfigure(1, weight=1)
        self.cockpit_unter = self._seitenkopf(seite, "Cockpit", "")

        # Das Pitboard
        tafel = ctk.CTkFrame(seite, fg_color=PITBOARD, corner_radius=16, border_width=2,
                             border_color=LINIE)
        tafel.grid(row=1, column=0, sticky="nsew", padx=(32, 12), pady=(0, 14))
        tafel.grid_columnconfigure(0, weight=1)
        innen = ctk.CTkFrame(tafel, fg_color="transparent")
        innen.grid(row=0, column=0, sticky="nsew", padx=30, pady=24)
        innen.grid_columnconfigure(1, weight=1)

        platzreihe = ctk.CTkFrame(innen, fg_color="transparent")
        platzreihe.grid(row=0, column=0, columnspan=2, sticky="w")
        self.pb_platz = ctk.CTkLabel(platzreihe, text="–", text_color=GELB,
                                     font=schrift(110, True, True), anchor="w")
        self.pb_platz.grid(row=0, column=0, sticky="sw")
        self.pb_gesamt = ctk.CTkLabel(platzreihe, text="", text_color=GEDAEMPFT,
                                      font=schrift(30, False, True), anchor="w")
        self.pb_gesamt.grid(row=0, column=1, sticky="sw", padx=(10, 0), pady=(0, 26))

        ctk.CTkFrame(innen, height=2, corner_radius=0, fg_color=LINIE).grid(row=1, column=0, columnspan=2,
                                                          sticky="ew", pady=(4, 14))
        self.pb_zeilen = {}
        for i, schluessel in enumerate(("vorne", "hinten")):
            wert = ctk.CTkLabel(innen, text="", text_color=TEXT, font=schrift(46, True, True),
                                anchor="w", width=190)
            wert.grid(row=2 + i, column=0, sticky="w")
            name = ctk.CTkLabel(innen, text="", text_color=GEDAEMPFT, font=schrift(17), anchor="w")
            name.grid(row=2 + i, column=1, sticky="w", padx=(18, 0))
            self.pb_zeilen[schluessel] = (wert, name)

        ctk.CTkFrame(innen, height=2, corner_radius=0, fg_color=LINIE).grid(row=4, column=0, columnspan=2,
                                                          sticky="ew", pady=(14, 12))
        fuss = ctk.CTkFrame(innen, fg_color="transparent")
        fuss.grid(row=5, column=0, columnspan=2, sticky="ew")
        self.pb_runde = ctk.CTkLabel(fuss, text="", text_color=TEXT, font=schrift(17, True), anchor="w")
        self.pb_runde.grid(row=0, column=0, sticky="w", padx=(0, 26))
        self.pb_letzte = ctk.CTkLabel(fuss, text="", text_color=GEDAEMPFT, font=schrift(15), anchor="w")
        self.pb_letzte.grid(row=0, column=1, sticky="w", padx=(0, 22))
        self.pb_beste = ctk.CTkLabel(fuss, text="", text_color=LILA, font=schrift(15), anchor="w")
        self.pb_beste.grid(row=0, column=2, sticky="w")
        self.pb_strecke = ctk.CTkLabel(innen, text="", text_color=GEDAEMPFT, font=schrift(14), anchor="w",
                                       justify="left")
        self.pb_strecke.grid(row=6, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # Letzter Funk
        funk = ctk.CTkFrame(seite, fg_color=TAFEL, corner_radius=16)
        funk.grid(row=1, column=1, sticky="nsew", padx=(0, 32), pady=(0, 14))
        funk.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(funk, text="Letzter Funk", text_color=TEXT, font=schrift(16, True), anchor="w"
                     ).grid(row=0, column=0, sticky="ew", padx=22, pady=(20, 10))
        self.kurzfunk = ctk.CTkFrame(funk, fg_color="transparent")
        self.kurzfunk.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 18))
        self.kurzfunk.grid_columnconfigure(0, weight=1)

        # Strategie-Leiste
        leiste = ctk.CTkFrame(seite, fg_color=TAFEL, corner_radius=16)
        leiste.grid(row=2, column=0, columnspan=2, sticky="ew", padx=32, pady=(0, 28))
        for i in range(3):
            leiste.grid_columnconfigure(i * 2, weight=1)
        self.strategie = {}
        felder = []
        for i, (schluessel, titel) in enumerate((("tank", "Tank"), ("box", "Boxenstopp"),
                                                 ("rest", "Restzeit"))):
            if i:
                ctk.CTkFrame(leiste, width=2, corner_radius=0, fg_color=LINIE).grid(row=0, column=i * 2 - 1,
                                                                  sticky="ns", pady=18)
            feld = ctk.CTkFrame(leiste, fg_color="transparent")
            feld.grid(row=0, column=i * 2, sticky="ew", padx=24, pady=18)
            felder.append(feld)
            feld.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(feld, text=titel, text_color=GEDAEMPFT, font=schrift(13), anchor="w"
                         ).grid(row=0, column=0, sticky="w")
            wert = ctk.CTkLabel(feld, text="–", text_color=TEXT, font=schrift(26, True, True), anchor="w")
            wert.grid(row=1, column=0, sticky="w")
            detail = ctk.CTkLabel(feld, text="", text_color=GEDAEMPFT, font=schrift(13), anchor="w")
            detail.grid(row=2, column=0, sticky="w")
            self.strategie[schluessel] = (wert, detail)
        self.tank_balken = ctk.CTkProgressBar(felder[0], height=6,
                                              corner_radius=3, progress_color=GELB, fg_color=LINIE)
        self.tank_balken.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.tank_balken.set(0)
        return seite

    def _cockpit_leer(self, text):
        self.pb_platz.configure(text="–")
        self.pb_gesamt.configure(text="")
        self.pb_zeilen["vorne"][0].configure(text="")
        self.pb_zeilen["vorne"][1].configure(text=text)
        self.pb_zeilen["hinten"][0].configure(text="")
        self.pb_zeilen["hinten"][1].configure(text="")
        for schluessel in ("runde", "letzte", "beste", "strecke"):
            getattr(self, "pb_" + schluessel).configure(text="")
        for wert, detail in self.strategie.values():
            wert.configure(text="–")
            detail.configure(text="")
        self.tank_balken.set(0)
        self.cockpit_unter.configure(text="Wartet auf eine Session")

    def _cockpit_zeigen(self, d):
        if not d.get("acc"):
            self._cockpit_leer("Warte auf ACC. Fahr auf die Strecke.")
            return
        self.cockpit_unter.configure(text=f'{d["session"]} in {d["strecke"]}')
        self.pb_platz.configure(text=f'P{d["platz"]}' if d.get("platz") else "–")
        self.pb_gesamt.configure(text=f'/ {d["gesamt"]}' if d.get("gesamt") else "")
        for schluessel in ("vorne", "hinten"):
            wert, name = self.pb_zeilen[schluessel]
            info = d.get(schluessel)
            if info:
                platz, fahrer, abstand = info
                wert.configure(text=abstand, text_color=TEXT)
                name.configure(text=f"P{platz} {fahrer}")
            elif schluessel == "vorne" and d.get("platz") == 1:
                wert.configure(text="Führung", text_color=GRUEN)
                name.configure(text="")
            elif schluessel == "vorne" and not d.get("zeitnahme"):
                wert.configure(text="")
                name.configure(text="Keine Verbindung zur Zeitnahme (broadcasting.json?)")
            else:
                wert.configure(text="")
                name.configure(text="")
        gesamt = f' von {d["runden_gesamt"]}' if d.get("runden_gesamt") else ""
        self.pb_runde.configure(text=f'Runde {d["runde"]}{gesamt}')
        self.pb_letzte.configure(text=f'Letzte {d["letzte"]}')
        self.pb_beste.configure(text=f'Beste {d["beste"]}')
        strecke = []
        for schluessel, wort in (("strecke_vorne", "vor dir"), ("strecke_hinten", "hinter dir")):
            if d.get(schluessel):
                name, abstand, runden = d[schluessel]
                zusatz = "" if not runden else (f", {runden:+d} R")
                strecke.append(f"{wort} {name} {abstand}{zusatz}")
        self.pb_strecke.configure(text=("Auf der Strecke: " + ",   ".join(strecke)) if strecke else "")

        wert, detail = self.strategie["tank"]
        wert.configure(text=f'{d["tank"]:.1f} L'.replace(".", ","))
        detail.configure(text=f'reicht {d["reicht"]:.1f} Runden'.replace(".", ",")
                         if d.get("reicht") else "Verbrauch wird gemessen")
        self.tank_balken.set(max(0.0, min(1.0, d["tank"] / d["tank_max"])))
        self.tank_balken.configure(progress_color=ROT if d.get("reicht", 99) < 2 else GELB)
        wert, detail = self.strategie["box"]
        wert.configure(text=d.get("box", "–"),
                       text_color=GRUEN if d.get("box") == "Kein Stopp nötig" else TEXT)
        detail.configure(text=d.get("box_detail", "nach einer vollen Runde"))
        wert, detail = self.strategie["rest"]
        wert.configure(text=d.get("rest", "–"))
        detail.configure(text=f'etwa {d["rest_runden"]:.0f} Runden'
                         if d.get("rest_runden") and not d.get("runden_gesamt") else "")

    # --- Live-Karte: Strecke, Rangliste, ein Fahrer im Fokus ----------------------
    def _seite_live(self):
        self.feld = {"autos": [], "karte": []}
        self.fokus = None                 # Index des Autos im Fokus (None = du selbst)
        self.live_zeilen = {}
        seite = ctk.CTkFrame(self.inhalt, fg_color="transparent")
        seite.grid_columnconfigure(0, weight=3, uniform="live")
        seite.grid_columnconfigure(1, weight=2, uniform="live")
        seite.grid_rowconfigure(1, weight=3)
        seite.grid_rowconfigure(2, weight=2)
        self.live_unter = self._seitenkopf(seite, "Live-Karte",
                                           "Wo alle gerade fahren. Klick auf einen Fahrer, um ihn genauer anzuschauen.")
        nebenknopf(seite, "Karte spiegeln", self._karte_spiegeln, 130).grid(row=0, column=1, sticky="e",
                                                                          padx=32, pady=(26, 0))
        # Karte
        tafel = ctk.CTkFrame(seite, fg_color=PITBOARD, corner_radius=16, border_width=2, border_color=LINIE)
        tafel.grid(row=1, column=0, sticky="nsew", padx=(32, 12), pady=(0, 12))
        tafel.grid_columnconfigure(0, weight=1)
        tafel.grid_rowconfigure(0, weight=1)
        self.karte = tk.Canvas(tafel, bg=PITBOARD, highlightthickness=0)
        self.karte.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.karte.bind("<Configure>", lambda _: self._karte_zeichnen())
        self.karte.bind("<Button-1>", self._karte_klick)
        # Rangliste
        liste = ctk.CTkFrame(seite, fg_color=TAFEL, corner_radius=16)
        liste.grid(row=1, column=1, rowspan=2, sticky="nsew", padx=(0, 32), pady=(0, 22))
        liste.grid_columnconfigure(0, weight=1)
        liste.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(liste, text="Rangliste", text_color=TEXT, font=schrift(16, True), anchor="w"
                     ).grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 6))
        self.live_liste = ctk.CTkScrollableFrame(liste, fg_color="transparent", scrollbar_button_color=LINIE,
                                                 scrollbar_button_hover_color=GEDAEMPFT)
        self.live_liste.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 10))
        self.live_liste.grid_columnconfigure(0, weight=1)
        # Fokus
        self.fokus_tafel = ctk.CTkFrame(seite, fg_color=TAFEL, corner_radius=16)
        self.fokus_tafel.grid(row=2, column=0, sticky="nsew", padx=(32, 12), pady=(0, 22))
        self.fokus_tafel.grid_columnconfigure(0, weight=1)
        self.fokus_tafel.grid_rowconfigure(1, weight=1)
        self.fokus_kopf = ctk.CTkLabel(self.fokus_tafel, text="", text_color=TEXT, font=schrift(14, True),
                                       anchor="w", justify="left")
        self.fokus_kopf.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 4))
        self.fokus_runden = ctk.CTkScrollableFrame(self.fokus_tafel, fg_color="transparent",
                                                   scrollbar_button_color=LINIE,
                                                   scrollbar_button_hover_color=GEDAEMPFT)
        self.fokus_runden.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 10))
        self._fokus_signatur = None
        return seite

    def _live_zeigen(self):
        autos = self.feld.get("autos", [])
        if not autos:
            self.live_unter.configure(text="Keine Daten. Starte den Ingenieur und fahr auf die Strecke "
                                           "(die Zeitnahme muss verbunden sein).")
        else:
            self.live_unter.configure(text="Klick auf einen Fahrer in der Liste oder auf der Karte, "
                                           "um seine Runden und Sektoren zu sehen.")
        self._rangliste_zeigen(autos)
        self._karte_zeichnen()
        self._fokus_zeigen()

    def _fokus_auto(self):
        autos = self.feld.get("autos", [])
        for auto in autos:
            if (self.fokus is None and auto["ich"]) or auto["index"] == self.fokus:
                return auto
        return None

    def _fokus_setzen(self, index):
        self.fokus = index
        self._fokus_signatur = None
        self._live_zeigen()

    def _rangliste_zeigen(self, autos):
        indizes = [a["index"] for a in autos]
        if indizes != list(self.live_zeilen):
            for zeile in self.live_zeilen.values():
                zeile[0].destroy()
            self.live_zeilen = {}
            for i, auto in enumerate(autos):
                rahmen = ctk.CTkFrame(self.live_liste, fg_color="transparent", corner_radius=8)
                rahmen.grid(row=i, column=0, sticky="ew", pady=1)
                rahmen.grid_columnconfigure(1, weight=1)
                platz = ctk.CTkLabel(rahmen, text="", width=34, font=schrift(13, True, True), anchor="e")
                platz.grid(row=0, column=0, padx=(6, 8), pady=4)
                name = ctk.CTkLabel(rahmen, text="", font=schrift(13), anchor="w", width=175)
                name.grid(row=0, column=1, sticky="w")
                abstand = ctk.CTkLabel(rahmen, text="", font=schrift(13, False, True), anchor="e", width=70)
                abstand.grid(row=0, column=2, padx=(6, 10))
                for w in (rahmen, platz, name, abstand):
                    w.bind("<Button-1>", lambda _, idx=auto["index"]: self._fokus_setzen(idx))
                self.live_zeilen[auto["index"]] = (rahmen, platz, name, abstand)
        fokus = self._fokus_auto()
        for auto in autos:
            rahmen, platz, name, abstand = self.live_zeilen[auto["index"]]
            gewaehlt = fokus is not None and auto["index"] == fokus["index"]
            rahmen.configure(fg_color=TAFEL_HELL if gewaehlt else "transparent")
            farbe = GELB if auto["ich"] else (GEDAEMPFT if auto["box"] else TEXT)
            platz.configure(text=f"P{auto['platz']}", text_color=farbe)
            nummer = f"#{auto['nummer']}  " if auto["nummer"] is not None else ""
            name.configure(text=f"{nummer}{auto['fahrer']}" + ("  (Box)" if auto["box"] else ""), text_color=farbe)
            abstand.configure(text="Du" if auto["ich"] else auto["abstand"], text_color=farbe)

    def _karten_umrechnung(self):
        """Gibt eine Funktion zurück, die Weltkoordinaten auf die Karte umrechnet."""
        c = self.karte
        breite, hoehe = c.winfo_width(), c.winfo_height()
        punkte = list(self.feld.get("karte", []))
        punkte += [(a["x"], a["y"]) for a in self.feld.get("autos", []) if a["x"] is not None]
        if len(punkte) < 2 or breite < 50:
            return None
        xs, ys = [p[0] for p in punkte], [p[1] for p in punkte]
        min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
        spanne = max(max_x - min_x, max_y - min_y, 1.0)
        rand = 24
        massstab = min((breite - 2 * rand) / max(max_x - min_x, 1.0), (hoehe - 2 * rand) / max(max_y - min_y, 1.0))
        if spanne < 1 or massstab <= 0:
            return None
        versatz_x = (breite - (max_x - min_x) * massstab) / 2
        versatz_y = (hoehe - (max_y - min_y) * massstab) / 2
        spiegeln = self.e.get("karte_spiegeln", False)
        if spiegeln:
            return lambda x, y: (versatz_x + (x - min_x) * massstab, hoehe - versatz_y - (y - min_y) * massstab)
        return lambda x, y: (versatz_x + (x - min_x) * massstab, versatz_y + (y - min_y) * massstab)

    def _karte_spiegeln(self):
        """Falls die Strecke spiegelverkehrt aussieht: umdrehen und merken."""
        self.e["karte_spiegeln"] = not self.e.get("karte_spiegeln", False)
        einstellungen_speichern(self.e)
        self._karte_zeichnen()

    def _karte_zeichnen(self):
        c = self.karte
        c.delete("all")
        umrechnen = self._karten_umrechnung()
        if umrechnen is None:
            c.create_text(c.winfo_width() / 2, c.winfo_height() / 2, fill=GEDAEMPFT, font=(SCHRIFT, 12),
                          text="Die Karte zeichnet sich von selbst, sobald Autos auf der Strecke fahren.")
            return
        karte = self.feld.get("karte", [])
        if len(karte) > 2:
            punkte = [umrechnen(x, y) for x, y in karte]
            flach = [wert for punkt in punkte + punkte[:1] for wert in punkt]
            c.create_line(*flach, fill=LINIE, width=12, capstyle="round", joinstyle="round", smooth=True)
            c.create_line(*flach, fill=TAFEL_HELL, width=6, capstyle="round", joinstyle="round", smooth=True)
            sx, sy = punkte[0]
            c.create_line(sx - 9, sy, sx + 9, sy, fill=TEXT, width=3)          # Start/Ziel
        fokus = self._fokus_auto()
        self._karten_autos = []
        reihenfolge = sorted(self.feld.get("autos", []), key=lambda a: (a["ich"], fokus is not None and a["index"] == fokus["index"]))
        for auto in reihenfolge:
            if auto["x"] is None:
                continue
            x, y = umrechnen(auto["x"], auto["y"])
            ist_fokus = fokus is not None and auto["index"] == fokus["index"]
            if auto["ich"]:
                farbe, text_farbe, r = GELB, DUNKEL_TEXT, 11
            elif auto["box"]:
                farbe, text_farbe, r = LINIE, GEDAEMPFT, 8
            else:
                farbe, text_farbe, r = TEXT, DUNKEL_TEXT, 9
            if ist_fokus and not auto["ich"]:
                farbe = LILA
            if ist_fokus:
                c.create_oval(x - r - 5, y - r - 5, x + r + 5, y + r + 5, outline=LILA, width=2)
            c.create_oval(x - r, y - r, x + r, y + r, fill=farbe, outline=PITBOARD, width=2)
            c.create_text(x, y, text=str(auto["platz"]), fill=text_farbe, font=(SCHRIFT, 8 if r < 10 else 9, "bold"))
            self._karten_autos.append((x, y, auto["index"]))

    def _karte_klick(self, ereignis):
        naechstes = None
        for x, y, index in getattr(self, "_karten_autos", []):
            abstand = (x - ereignis.x) ** 2 + (y - ereignis.y) ** 2
            if abstand < 400 and (naechstes is None or abstand < naechstes[0]):
                naechstes = (abstand, index)
        if naechstes:
            self._fokus_setzen(naechstes[1])

    def _fokus_zeigen(self):
        auto = self._fokus_auto()
        if auto is None:
            self.fokus_kopf.configure(text="Kein Fahrer ausgewählt")
            for kind in self.fokus_runden.winfo_children():
                kind.destroy()
            self._fokus_signatur = None
            return
        wer = "Du" if auto["ich"] else auto["fahrer"]
        teile = [f"P{auto['platz']}  {wer}"]
        if auto["abstand"]:
            teile.append(f"Abstand {auto['abstand']} s" if "R" not in auto["abstand"] else f"Abstand {auto['abstand']}")
        teile.append(f"Beste {zeit_anzeige(auto['beste'])}")
        teile.append(f"Stopps {auto['stopps']}")
        self.fokus_kopf.configure(text="    ".join(teile))
        signatur = (auto["index"], len(auto["runden"]), auto["beste"])
        if signatur == self._fokus_signatur:
            return                                          # Tabelle hat sich nicht geändert
        self._fokus_signatur = signatur
        for kind in self.fokus_runden.winfo_children():
            kind.destroy()
        spalten = ["Runde", "Zeit", "Sektor 1", "Sektor 2", "Sektor 3"]
        for i, titel in enumerate(spalten):
            self.fokus_runden.grid_columnconfigure(i, weight=1)
            ctk.CTkLabel(self.fokus_runden, text=titel, text_color=GEDAEMPFT, font=schrift(12, True), anchor="w"
                         ).grid(row=0, column=i, sticky="w", padx=10, pady=(4, 2))
        runden = auto["runden"]
        if not runden:
            ctk.CTkLabel(self.fokus_runden, text="Noch keine fertige Runde gesehen.", text_color=GEDAEMPFT,
                         font=schrift(13)).grid(row=1, column=0, columnspan=5, sticky="w", padx=10, pady=6)
            return
        gueltige = [r for r in runden if r["gueltig"]]
        beste_zeit = min((r["zeit"] for r in gueltige), default=None)
        beste_sektoren = []
        for r in gueltige:
            for i, z in enumerate(r["sektoren"]):
                if z:
                    if i >= len(beste_sektoren):
                        beste_sektoren.append(z)
                    elif z < beste_sektoren[i]:
                        beste_sektoren[i] = z
        for zeile, r in enumerate(reversed(runden), start=1):
            grundfarbe = ROT if not r["gueltig"] else (GEDAEMPFT if r.get("box") else TEXT)
            zeitfarbe = LILA if r["gueltig"] and r["zeit"] == beste_zeit else grundfarbe
            werte = [(str(r["runde"]), grundfarbe),
                     (zeit_anzeige(r["zeit"]) + ("" if r["gueltig"] else " (ungültig)"), zeitfarbe)]
            for i in range(3):
                z = r["sektoren"][i] if i < len(r["sektoren"]) else None
                farbe = LILA if (z and r["gueltig"] and i < len(beste_sektoren) and z == beste_sektoren[i]) else grundfarbe
                werte.append((f"{z / 1000:.3f}".replace(".", ",") if z else "–", farbe))
            for spalte, (text, farbe) in enumerate(werte):
                ctk.CTkLabel(self.fokus_runden, text=text, text_color=farbe, font=schrift(13, False, spalte > 0),
                             anchor="w").grid(row=zeile, column=spalte, sticky="w", padx=10, pady=1)

    # --- Funk --------------------------------------------------------------
    def _seite_funk(self):
        seite = ctk.CTkFrame(self.inhalt, fg_color="transparent")
        seite.grid_columnconfigure(0, weight=1)
        seite.grid_rowconfigure(1, weight=1)
        self._seitenkopf(seite, "Funk", "Alles, was du gesagt hast und was der Ingenieur gefunkt hat")
        self.funk_liste = ctk.CTkScrollableFrame(seite, fg_color=TAFEL, corner_radius=16,
                                                 scrollbar_button_color=LINIE,
                                                 scrollbar_button_hover_color=GEDAEMPFT)
        self.funk_liste.grid(row=1, column=0, sticky="nsew", padx=32, pady=(0, 28))
        self.funk_liste.grid_columnconfigure(0, weight=1)
        return seite

    def _funk_eintrag(self, art, text):
        uhrzeit = time.strftime("%H:%M")
        zeile = ctk.CTkFrame(self.funk_liste, fg_color="transparent")
        zeile.grid(row=len(self.funk_zeilen), column=0, sticky="ew", padx=14, pady=5)
        zeile.grid_columnconfigure(0, weight=1)
        if art in ("system", "fehler", "zeit"):
            ctk.CTkLabel(zeile, text=f"{text}   {uhrzeit}", text_color=ROT if art == "fehler" else GEDAEMPFT,
                         font=schrift(12), wraplength=560).grid(row=0, column=0)
        else:
            du = art == "du"
            blase = ctk.CTkFrame(zeile, corner_radius=14,
                                 fg_color=TAFEL_HELL if du else GELB_DUNKEL)
            blase.grid(row=0, column=0, sticky="e" if du else "w", padx=(120, 0) if du else (0, 120))
            ing = self.e.get("ingenieur_name") or "Ingenieur"
            wer = {"du": "Du", "ingenieur": ing, "ansage": f"{ing}, von selbst"}[art]
            ctk.CTkLabel(blase, text=f"{wer}   {uhrzeit}", text_color=GEDAEMPFT if du else GELB,
                         font=schrift(11), anchor="w").grid(row=0, column=0, sticky="w", padx=16, pady=(10, 0))
            ctk.CTkLabel(blase, text=text, text_color=TEXT, font=schrift(14), anchor="w",
                         justify="left", wraplength=520).grid(row=1, column=0, sticky="w", padx=16, pady=(2, 12))
        self.funk_zeilen.append((art, text, uhrzeit, zeile))
        if len(self.funk_zeilen) > 200:                 # alte Einträge wegräumen
            self.funk_zeilen.pop(0)[3].destroy()
        self._kurzfunk_zeigen()
        self.root.after(50, self._funk_nach_unten)

    def _funk_nach_unten(self):
        try:
            self.funk_liste._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _kurzfunk_zeigen(self):
        for kind in self.kurzfunk.winfo_children():
            kind.destroy()
        wichtige = [z for z in self.funk_zeilen if z[0] not in ("system", "zeit")][-4:]
        if not wichtige:
            ctk.CTkLabel(self.kurzfunk, text="Noch kein Funk. Halte die Funktaste und frag zum "
                                             "Beispiel nach dem Sprit.", text_color=GEDAEMPFT,
                         font=schrift(13), anchor="w", justify="left", wraplength=320
                         ).grid(row=0, column=0, sticky="w")
            return
        for i, (art, text, uhrzeit, _) in enumerate(wichtige):
            wer = "Du" if art == "du" else ("Fehler" if art == "fehler" else (self.e.get("ingenieur_name") or "Ingenieur"))
            farbe = GEDAEMPFT if art == "du" else (ROT if art == "fehler" else GELB)
            ctk.CTkLabel(self.kurzfunk, text=f"{wer}   {uhrzeit}", text_color=farbe, font=schrift(11),
                         anchor="w").grid(row=i * 2, column=0, sticky="w", pady=(10 if i else 0, 0))
            ctk.CTkLabel(self.kurzfunk, text=text, text_color=TEXT, font=schrift(14), anchor="w",
                         justify="left", wraplength=330).grid(row=i * 2 + 1, column=0, sticky="w")

    # --- Ansagen -----------------------------------------------------------
    # --- Auswertung: Rundenzeiten als Diagramm und Tabelle --------------------
    def _seite_auswertung(self):
        self.aktuelle_session = None
        self.auswertung_daten = None
        seite = ctk.CTkFrame(self.inhalt, fg_color="transparent")
        seite.grid_columnconfigure(0, weight=1)
        seite.grid_rowconfigure(3, weight=1)
        self.auswertung_unter = self._seitenkopf(seite, "Auswertung",
                                                 "Deine Runden der aktuellen oder einer gespeicherten Session")
        leiste = ctk.CTkFrame(seite, fg_color="transparent")
        leiste.grid(row=0, column=0, sticky="e", padx=32, pady=(26, 0))
        self.auswertung_quelle = ctk.CTkOptionMenu(
            leiste, values=["Aktuelle Session"], width=320, height=34, font=schrift(13),
            fg_color=TAFEL_HELL, button_color=LINIE, button_hover_color=GEDAEMPFT,
            dropdown_fg_color=TAFEL, text_color=TEXT, command=self._auswertung_gewaehlt)
        self.auswertung_quelle.grid(row=0, column=0)
        nebenknopf(leiste, "Ordner öffnen", self._auswertung_ordner, 130).grid(row=0, column=1, padx=(8, 0))

        # Kacheln mit den wichtigsten Zahlen
        kacheln = ctk.CTkFrame(seite, fg_color="transparent")
        kacheln.grid(row=1, column=0, sticky="ew", padx=26)
        self.kacheln = {}
        for i, (schluessel, titel) in enumerate((("bestzeit", "Bestzeit"), ("runden", "Runden"),
                                                  ("konstanz", "Konstanz (5 Runden)"), ("trend", "Trend"),
                                                  ("platz", "Start / Ziel"), ("stopps", "Stopps / Strafen"))):
            kacheln.grid_columnconfigure(i, weight=1, uniform="kachel")
            kachel = ctk.CTkFrame(kacheln, fg_color=TAFEL, corner_radius=12)
            kachel.grid(row=0, column=i, sticky="ew", padx=6)
            ctk.CTkLabel(kachel, text=titel, text_color=GEDAEMPFT, font=schrift(11), anchor="w"
                         ).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 0))
            wert = ctk.CTkLabel(kachel, text="–", text_color=TEXT, font=schrift(18, True, True), anchor="w")
            wert.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 10))
            self.kacheln[schluessel] = wert

        # Diagramm
        tafel = ctk.CTkFrame(seite, fg_color=TAFEL, corner_radius=16)
        tafel.grid(row=2, column=0, sticky="ew", padx=32, pady=(14, 0))
        tafel.grid_columnconfigure(0, weight=1)
        self.diagramm = tk.Canvas(tafel, height=230, bg=TAFEL, highlightthickness=0)
        self.diagramm.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        self.diagramm.bind("<Configure>", lambda _: self._diagramm_zeichnen())

        # Tabelle
        self.tabelle = ctk.CTkScrollableFrame(seite, fg_color=TAFEL, corner_radius=16,
                                              scrollbar_button_color=LINIE,
                                              scrollbar_button_hover_color=GEDAEMPFT)
        self.tabelle.grid(row=3, column=0, sticky="nsew", padx=32, pady=(14, 22))
        self._auswertung_zeigen(None)
        return seite

    def _auswertung_liste(self):
        """Gespeicherte Sessions im Ordner 'rennen' in die Auswahl eintragen."""
        try:
            dateien = sorted((d for d in os.listdir(acc_protokoll.RENNEN_ORDNER) if d.endswith(".json")),
                             reverse=True)[:40]
        except OSError:
            dateien = []
        self.auswertung_quelle.configure(values=["Aktuelle Session"] + [d[:-5].replace("_", "  ") for d in dateien])
        self._auswertung_dateinamen = {d[:-5].replace("_", "  "): d for d in dateien}

    def _auswertung_gewaehlt(self, wahl):
        if wahl == "Aktuelle Session":
            self._auswertung_zeigen(self.aktuelle_session)
            return
        try:
            with open(os.path.join(acc_protokoll.RENNEN_ORDNER, self._auswertung_dateinamen[wahl]),
                      encoding="utf-8") as datei:
                self._auswertung_zeigen(json.load(datei))
        except (OSError, ValueError, KeyError):
            self._auswertung_zeigen(None)

    def _auswertung_ordner(self):
        os.makedirs(acc_protokoll.RENNEN_ORDNER, exist_ok=True)
        try:
            os.startfile(acc_protokoll.RENNEN_ORDNER)
        except Exception:
            pass

    def _auswertung_zeigen(self, daten):
        self.auswertung_daten = daten
        for kind in self.tabelle.winfo_children():
            kind.destroy()
        if not daten or not daten.get("runden"):
            for wert in self.kacheln.values():
                wert.configure(text="–")
            ctk.CTkLabel(self.tabelle, text="Noch keine Runden. Sobald du fährst, erscheinen sie hier. "
                                            "Nach jeder Session wird alles im Ordner 'rennen' gespeichert.",
                         text_color=GEDAEMPFT, font=schrift(13), wraplength=700, justify="left"
                         ).grid(row=0, column=0, sticky="w", padx=16, pady=16)
            self._diagramm_zeichnen()
            return
        runden = daten["runden"]
        strecke = str(daten.get("strecke", "")).replace("_", " ").title()
        datum = time.strftime("%d.%m.%Y %H:%M", time.localtime(daten.get("beginn") or time.time()))
        self.auswertung_unter.configure(text=f"{daten.get('session', '')} in {strecke}, {datum}")
        self.kacheln["bestzeit"].configure(text=zeit_anzeige(daten.get("bestzeit")))
        self.kacheln["runden"].configure(text=str(len(runden)))
        konstanz = daten.get("konstanz")
        self.kacheln["konstanz"].configure(text=f"±{konstanz / 2:.2f} s".replace(".", ",") if konstanz is not None else "–")
        trend = daten.get("trend")
        self.kacheln["trend"].configure(
            text=(f"{trend:+.2f} s/Rd".replace(".", ",") if trend is not None else "–"),
            text_color=(ROT if trend and trend > 0.15 else GRUEN if trend is not None and trend < 0 else TEXT))
        start, ziel = daten.get("startplatz"), daten.get("endplatz")
        letzter_platz = next((r["platz"] for r in reversed(runden) if r.get("platz")), None)
        self.kacheln["platz"].configure(text=f"P{start or '–'} → P{ziel or letzter_platz or '–'}")
        self.kacheln["stopps"].configure(text=f"{daten.get('stopps', 0)} / {daten.get('strafen', 0)}")

        # Tabelle
        spalten = ["Runde", "Zeit", "Abstand", "Sektor 1", "Sektor 2", "Sektor 3", "Platz", "Tank"]
        for i, titel in enumerate(spalten):
            self.tabelle.grid_columnconfigure(i, weight=1)
            ctk.CTkLabel(self.tabelle, text=titel, text_color=GEDAEMPFT, font=schrift(12, True), anchor="w"
                         ).grid(row=0, column=i, sticky="w", padx=10, pady=(10, 4))
        beste = daten.get("bestzeit")
        beste_sektoren = []
        for runde in runden:
            if runde["gueltig"]:
                for i, zeit in enumerate(runde.get("sektoren") or []):
                    if zeit and (i >= len(beste_sektoren) or zeit < beste_sektoren[i]):
                        if i >= len(beste_sektoren):
                            beste_sektoren.append(zeit)
                        else:
                            beste_sektoren[i] = zeit
        for zeile, runde in enumerate(reversed(runden), start=1):
            ist_beste = runde["zeit"] == beste and runde["gueltig"]
            farbe = LILA if ist_beste else (ROT if not runde["gueltig"] else (GEDAEMPFT if runde["box"] else TEXT))
            abstand = "" if not beste or ist_beste else f"+{(runde['zeit'] - beste) / 1000:.3f}".replace(".", ",")
            zusatz = " (Box)" if runde["box"] else (" (ungültig)" if not runde["gueltig"] else "")
            werte = [str(runde["nummer"]), zeit_anzeige(runde["zeit"]) + zusatz, abstand]
            sektoren = runde.get("sektoren") or []
            for i in range(3):
                werte.append(f"{sektoren[i] / 1000:.3f}".replace(".", ",") if i < len(sektoren) and sektoren[i] else "–")
            werte += [f"P{runde['platz']}" if runde.get("platz") else "–",
                      f"{runde['tank']:.1f} l".replace(".", ",") if runde.get("tank") is not None else "–"]
            for i, wert in enumerate(werte):
                f = farbe
                if 3 <= i <= 5 and i - 3 < len(sektoren) and i - 3 < len(beste_sektoren) \
                        and sektoren[i - 3] and sektoren[i - 3] == beste_sektoren[i - 3] and runde["gueltig"]:
                    f = LILA
                ctk.CTkLabel(self.tabelle, text=wert, text_color=f, font=schrift(13, False, i in (1, 2, 3, 4, 5)),
                             anchor="w").grid(row=zeile, column=i, sticky="w", padx=10, pady=1)
        self._diagramm_zeichnen()

    def _diagramm_zeichnen(self):
        c = self.diagramm
        c.delete("all")
        breite, hoehe = c.winfo_width(), c.winfo_height()
        daten = self.auswertung_daten
        runden = daten.get("runden") if daten else None
        if not runden or breite < 50:
            c.create_text(breite / 2, hoehe / 2, text="Hier erscheint das Diagramm deiner Rundenzeiten.",
                          fill=GEDAEMPFT, font=(SCHRIFT, 12))
            return
        links, rechts, oben, unten = 70, 20, 16, 30
        # Achse: saubere Runden bestimmen den Bereich, Ausreißer (Box, Unfall) werden oben abgeschnitten
        sauber = [r["zeit"] for r in runden if r["gueltig"] and not r["box"]] or [r["zeit"] for r in runden]
        unten_wert = min(sauber)
        sauber_sortiert = sorted(sauber)
        oben_wert = max(sauber_sortiert[int(len(sauber_sortiert) * 0.9)] , unten_wert + 1000)
        oben_wert += (oben_wert - unten_wert) * 0.15
        unten_wert -= (oben_wert - unten_wert) * 0.1

        def y(zeit):
            zeit = min(max(zeit, unten_wert), oben_wert)
            return oben + (zeit - unten_wert) / (oben_wert - unten_wert) * (hoehe - oben - unten)

        def x(i):
            if len(runden) == 1:
                return (links + breite - rechts) / 2
            return links + i / (len(runden) - 1) * (breite - links - rechts)

        # Hilfslinien mit Beschriftung
        for k in range(5):
            wert = unten_wert + (oben_wert - unten_wert) * k / 4
            c.create_line(links, y(wert), breite - rechts, y(wert), fill=LINIE)
            c.create_text(links - 8, y(wert), text=zeit_anzeige(wert), anchor="e", fill=GEDAEMPFT,
                          font=(SCHRIFT, 9))
        schritt = max(1, len(runden) // 12)
        for i, runde in enumerate(runden):
            if i % schritt == 0 or i == len(runden) - 1:
                c.create_text(x(i), hoehe - unten + 14, text=str(runde["nummer"]), fill=GEDAEMPFT,
                              font=(SCHRIFT, 9))
        # Linie durch die gültigen Runden ohne Box
        punkte = []
        for i, runde in enumerate(runden):
            if runde["gueltig"] and not runde["box"]:
                punkte += [x(i), y(runde["zeit"])]
        if len(punkte) >= 4:
            c.create_line(*punkte, fill=GELB, width=2, smooth=False)
        beste = daten.get("bestzeit")
        for i, runde in enumerate(runden):
            farbe = (LILA if runde["zeit"] == beste and runde["gueltig"] else
                     ROT if not runde["gueltig"] else GEDAEMPFT if runde["box"] else GELB)
            r = 5 if farbe == LILA else 3.5
            c.create_oval(x(i) - r, y(runde["zeit"]) - r, x(i) + r, y(runde["zeit"]) + r, fill=farbe, outline="")
        # Legende
        for k, (text, farbe) in enumerate((("Bestzeit", LILA), ("ungültig", ROT), ("mit Box", GEDAEMPFT))):
            px = breite - rechts - 250 + k * 85
            c.create_oval(px, oben - 2, px + 8, oben + 6, fill=farbe, outline="")
            c.create_text(px + 12, oben + 2, text=text, anchor="w", fill=GEDAEMPFT, font=(SCHRIFT, 9))

    def _seite_ansagen(self):
        seite = ctk.CTkFrame(self.inhalt, fg_color="transparent")
        seite.grid_columnconfigure(0, weight=1)
        self._seitenkopf(seite, "Ansagen", "Worüber sich der Ingenieur von selbst meldet")
        oben = ctk.CTkFrame(seite, fg_color=TAFEL, corner_radius=16)
        oben.grid(row=1, column=0, sticky="ew", padx=32, pady=(0, 12))
        oben.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(oben, text="Wie gesprächig?", text_color=TEXT, font=schrift(15, True), anchor="w"
                     ).grid(row=0, column=0, sticky="w", padx=24, pady=(16, 0))
        ctk.CTkLabel(oben, text="Ruhig: fast nur Wichtiges. Normal: ab und zu ein Rundenbericht. "
                                "Viel: fast jede Runde etwas.", text_color=GEDAEMPFT, font=schrift(12),
                     anchor="w").grid(row=1, column=0, sticky="w", padx=24, pady=(0, 16))
        self.gespraechig = Auswahl(oben, GESPRAECHIG_STUFEN,
                                   GESPRAECHIG_STUFEN[int(self.e.get("gespraechig", 1))],
                                   lambda _: self._speichern())
        self.gespraechig.grid(row=0, column=1, rowspan=2, sticky="e", padx=24)
        tafel = ctk.CTkFrame(seite, fg_color=TAFEL, corner_radius=16)
        tafel.grid(row=2, column=0, sticky="ew", padx=32)
        tafel.grid_columnconfigure((0, 1), weight=1)
        self.ansagen_schalter = {}
        for i, (schluessel, text, _) in enumerate(ANSAGEN):
            variable = tk.BooleanVar(value=self.e["ansagen"].get(schluessel, False))
            self.ansagen_schalter[schluessel] = variable
            ctk.CTkSwitch(tafel, text=text, variable=variable, command=self._speichern,
                          progress_color=GELB, button_color=TEXT, button_hover_color=TEXT,
                          fg_color=LINIE, text_color=TEXT, font=schrift(14)
                          ).grid(row=i // 2, column=i % 2, sticky="w", padx=24,
                                 pady=(18 if i < 2 else 9, 18 if i >= len(ANSAGEN) - 2 else 9))
        ctk.CTkLabel(seite, text='Während der Fahrt per Funk: "Funkstille" lässt nur noch Dringendes '
                                 'durch (Flaggen, Pitlimiter, Box). "Ansagen wieder an" schaltet alles '
                                 'wieder ein.', text_color=GEDAEMPFT, font=schrift(13), anchor="w",
                     justify="left", wraplength=760).grid(row=3, column=0, sticky="w", padx=34, pady=16)
        return seite

    # --- Einstellungen -----------------------------------------------------
    def _seite_einstellungen(self):
        seite = ctk.CTkFrame(self.inhalt, fg_color="transparent")
        seite.grid_columnconfigure(0, weight=1)
        seite.grid_rowconfigure(1, weight=1)
        self.einstellung_hinweis = self._seitenkopf(seite, "Einstellungen",
                                                    "Wird automatisch gespeichert")
        rollen = ctk.CTkScrollableFrame(seite, fg_color="transparent",
                                        scrollbar_button_color=LINIE,
                                        scrollbar_button_hover_color=GEDAEMPFT)
        rollen.grid(row=1, column=0, sticky="nsew", padx=(20, 20), pady=(0, 20))
        rollen.grid_columnconfigure(0, weight=1)
        abschnitt_nr = [0]

        def abschnitt(titel):
            ctk.CTkLabel(rollen, text=titel, text_color=TEXT, font=schrift(17, True), anchor="w"
                         ).grid(row=abschnitt_nr[0] * 2, column=0, sticky="w", padx=12,
                                pady=(6 if abschnitt_nr[0] == 0 else 22, 8))
            tafel = ctk.CTkFrame(rollen, fg_color=TAFEL, corner_radius=16)
            tafel.grid(row=abschnitt_nr[0] * 2 + 1, column=0, sticky="ew", padx=12)
            tafel.grid_columnconfigure(1, weight=1)
            abschnitt_nr[0] += 1
            tafel.zeilen = 0
            return tafel

        def zeile(tafel, titel, hinweis=None):
            n = tafel.zeilen
            erste = n == 0
            box = ctk.CTkFrame(tafel, fg_color="transparent")
            box.grid(row=n, column=0, sticky="nw", padx=(24, 16), pady=(20 if erste else 10, 10))
            ctk.CTkLabel(box, text=titel, text_color=TEXT, font=schrift(14), anchor="w").grid(
                row=0, column=0, sticky="w")
            if hinweis:
                ctk.CTkLabel(box, text=hinweis, text_color=GEDAEMPFT, font=schrift(11), anchor="w",
                             justify="left", wraplength=190).grid(row=1, column=0, sticky="w")
            platz = ctk.CTkFrame(tafel, fg_color="transparent")
            platz.grid(row=n, column=1, sticky="w", padx=(0, 24), pady=(20 if erste else 10, 10))
            tafel.zeilen += 1
            return platz

        # Stimme und Funk
        tafel = abschnitt("Stimme und Funk")
        platz = zeile(tafel, "Stimme", "Piper klingt natürlicher und wird einmalig geladen")
        self.stimmen = stimmen_liste()
        self.stimme = tk.StringVar(value=self._stimmen_anzeige(self.e["stimme"]))
        self.stimm_auswahl = auswahlmenue(platz, self.stimme,
                                          [self._stimmen_text(s) for s in self.stimmen],
                                          lambda _: self._stimme_gewaehlt(), breite=420)
        self.stimm_auswahl.grid(row=0, column=0)
        self.download_knopf = nebenknopf(platz, "Laden", self._stimme_laden, 80)
        self.download_knopf.grid(row=0, column=1, padx=(8, 0))
        nebenknopf(platz, "Anhören", self._stimme_testen, 90).grid(row=0, column=2, padx=(8, 0))
        self.download_text = ctk.CTkLabel(platz, text="", text_color=GELB, font=schrift(12), anchor="w")
        self.download_text.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        platz = zeile(tafel, "Aussprache", "Wie Abkürzungen und englische Wörter gesprochen werden")
        nebenknopf(platz, "Wörterbuch bearbeiten", self._aussprache_oeffnen, 200).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(platz, text="Öffnet aussprache.json im Editor", text_color=GEDAEMPFT,
                     font=schrift(12)).grid(row=0, column=1, padx=(12, 0))

        platz = zeile(tafel, "Funk-Effekt", "Klingt wie Boxenfunk im Helm")
        self.funk = Auswahl(platz, [s.capitalize() for s in FUNK_STUFEN],
                            FUNK_STUFEN[self.e["funk"]].capitalize(), lambda _: self._speichern())
        self.funk.grid(row=0, column=0, sticky="w")

        self.tempo = tk.IntVar(value=self.e["tempo"])
        self.lautstaerke = tk.IntVar(value=self.e["lautstaerke"])
        for titel, variable, von, bis in (("Sprechtempo", self.tempo, -5, 10),
                                          ("Lautstärke", self.lautstaerke, 0, 100)):
            platz = zeile(tafel, titel)
            anzeige = ctk.CTkLabel(platz, text=str(variable.get()), text_color=GEDAEMPFT,
                                   font=schrift(13), width=40)

            def bewegt(wert, variable=variable, anzeige=anzeige):
                variable.set(int(round(float(wert))))
                anzeige.configure(text=str(variable.get()))
                self._spaeter_speichern()

            regler = ctk.CTkSlider(platz, from_=von, to=bis, number_of_steps=bis - von, width=300,
                                   command=bewegt, button_color=GELB, button_hover_color=GELB_HOVER,
                                   progress_color=GELB, fg_color=LINIE)
            regler.set(variable.get())
            regler.grid(row=0, column=0)
            anzeige.grid(row=0, column=1, padx=(10, 0))

        platz = zeile(tafel, "Name des Ingenieurs", "So meldet er sich am Funk")
        namen = list(INGENIEUR_NAMEN)
        if self.e.get("ingenieur_name") and self.e["ingenieur_name"] not in namen:
            namen.append(self.e["ingenieur_name"])
        self.ingenieur_name = Auswahl(platz, namen, self.e.get("ingenieur_name") or INGENIEUR_NAMEN[0],
                                      lambda _: self._speichern())
        self.ingenieur_name.grid(row=0, column=0, sticky="w")

        platz = zeile(tafel, "Dein Name", "So spricht dich der Ingenieur an (leer = ohne Namen)")
        self.fahrer_name = ctk.CTkEntry(platz, width=200, height=32, font=schrift(13),
                                        fg_color=TAFEL_HELL, border_color=LINIE, text_color=TEXT)
        self.fahrer_name.insert(0, self.e.get("fahrer_name", ""))
        self.fahrer_name.grid(row=0, column=0, sticky="w")
        self.fahrer_name.bind("<KeyRelease>", lambda _: self._spaeter_speichern())

        platz = zeile(tafel, "Begrüßung", "Beim Start meldet sich der Ingenieur mit einem Funk-Check")
        self.begruessung = tk.BooleanVar(value=self.e["begruessung"])
        ctk.CTkSwitch(platz, text="", variable=self.begruessung, command=self._speichern,
                      progress_color=GELB, button_color=TEXT, button_hover_color=TEXT,
                      fg_color=LINIE).grid(row=0, column=0, sticky="w")

        # Steuerung
        tafel = abschnitt("Steuerung")
        platz = zeile(tafel, "Funktaste", "Taste am Lenkrad, Steuerkreuz oder Tastatur")
        self.funk_label = ctk.CTkLabel(platz, text=acc_funktaste.beschreibung(), text_color=TEXT,
                                       font=schrift(13), anchor="w", width=300)
        self.funk_label.grid(row=0, column=0, sticky="w")
        self.lern_knopf = nebenknopf(platz, "Festlegen", self._funktaste_lernen, 100)
        self.lern_knopf.grid(row=0, column=1, padx=(8, 0))

        platz = zeile(tafel, "Mikrofon")
        self.mikrofone = ["Windows-Standard"] + mikrofone_auflisten()
        self.mikrofon = tk.StringVar(value=self.e["mikrofon"] or "Windows-Standard")
        auswahlmenue(platz, self.mikrofon, self.mikrofone, lambda _: self._speichern()).grid(row=0, column=0)

        platz = zeile(tafel, "Spracherkennung", "Größer ist genauer, aber langsamer")
        self.modell_texte = [f"{text} ({name})" for name, text in MODELLE]
        aktuell = next((t for t in self.modell_texte if t.endswith(f'({self.e["modell"]})')),
                       self.modell_texte[2])
        self.modell = tk.StringVar(value=aktuell)
        auswahlmenue(platz, self.modell, self.modell_texte, lambda _: self._speichern()).grid(row=0, column=0)

        # KI
        tafel = abschnitt("KI-Verständnis")
        platz = zeile(tafel, "KI benutzen", "Jede Frage geht an die KI. Sie bekommt alle Daten, versteht "
                                            "auch mehrere Fragen auf einmal und gibt Rat. Läuft "
                                            "kostenlos auf deiner Grafikkarte.")
        self.ki_an = tk.BooleanVar(value=self.e.get("ki", False))
        ctk.CTkSwitch(platz, text="", variable=self.ki_an, command=self._speichern,
                      progress_color=GELB, button_color=TEXT, button_hover_color=TEXT,
                      fg_color=LINIE, width=60).grid(row=0, column=0, sticky="w")
        self.ki_status = ctk.CTkLabel(platz, text="Prüfe ...", text_color=GEDAEMPFT, font=schrift(13),
                                      anchor="w")
        self.ki_status.grid(row=0, column=1, sticky="w", padx=(10, 0))

        platz = zeile(tafel, "Modell", "Größer ist klüger, aber langsamer")
        self.ki_texte = [text for _, text in acc_ki.KI_MODELLE]
        aktuell = next((text for name, text in acc_ki.KI_MODELLE if name == self.e.get("ki_modell")),
                       self.ki_texte[0])
        self.ki_modell = tk.StringVar(value=aktuell)
        auswahlmenue(platz, self.ki_modell, self.ki_texte,
                     lambda _: (self._speichern(), self._ki_pruefen()), breite=300).grid(row=0, column=0)
        self.ki_lade_knopf = nebenknopf(platz, "Modell laden", self._ki_laden, 120)
        self.ki_lade_knopf.grid(row=0, column=1, padx=(8, 0))

        platz = zeile(tafel, "Ollama", "Das Programm, das die KI ausführt. Einmal installieren, "
                                       "dann läuft es im Hintergrund.")
        nebenknopf(platz, "Ollama herunterladen", self._ollama_seite, 180).grid(row=0, column=0, sticky="w")
        nebenknopf(platz, "Erneut prüfen", self._ki_pruefen, 120).grid(row=0, column=1, padx=(8, 0))

        # Strategie
        tafel = abschnitt("Strategie")
        platz = zeile(tafel, "Sprit-Reserve", "So viele Runden Sprit sollen im Ziel übrig sein")
        reserve = min(RESERVEN, key=lambda r: abs(r - float(self.e["reserve_runden"])))
        self.reserve = Auswahl(platz, [self._reserve_text(r) for r in RESERVEN],
                               self._reserve_text(reserve), lambda _: self._speichern())
        self.reserve.grid(row=0, column=0, sticky="w")

        # Programm
        tafel = abschnitt("Programm")
        platz = zeile(tafel, "Desktop", "Starten per Doppelklick, ohne cmd")
        nebenknopf(platz, "Verknüpfung auf dem Desktop erstellen", self._verknuepfung, 300
                   ).grid(row=0, column=0, sticky="w")
        return seite

    @staticmethod
    def _reserve_text(wert):
        return f"{wert:g}".replace(".", ",")

    # --- Befehle -----------------------------------------------------------
    def _seite_befehle(self):
        seite = ctk.CTkFrame(self.inhalt, fg_color="transparent")
        seite.grid_columnconfigure(0, weight=1)
        seite.grid_rowconfigure(1, weight=1)
        self._seitenkopf(seite, "Befehle", "Beispiele. Du musst nicht genau diese Sätze sagen, "
                                           "Stichwörter wie Sprit, Box oder P5 reichen.")
        rollen = ctk.CTkScrollableFrame(seite, fg_color="transparent", scrollbar_button_color=LINIE,
                                        scrollbar_button_hover_color=GEDAEMPFT)
        rollen.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        rollen.grid_columnconfigure((0, 1), weight=1, uniform="spalte")
        befehle = [
            ("Auf der Strecke", ["Wer ist auf der Strecke vor mir?", "Wer fährt auf der Strecke hinter mir?",
                                 "Wer ist vor mir und wie viel Abstand habe ich?"]),
            ("Abstände und Gegner", ["Abstand zum Vordermann", "Wer ist hinter mir?", "Abstand zu P3",
                                     "Abstand zum Führenden", "Wer ist Letzter?",
                                     "Bin ich schneller als der Vordermann?", "Wer hat die schnellste Runde?"]),
            ("Sprit und Boxenstopp", ["Wie viel Sprit habe ich?", "Wie viel verbrauche ich?",
                                      "Wann muss ich an die Box?", "Wie viel muss ich nachtanken?",
                                      "Schaffe ich es ohne Stopp?", "Pflichtstopp erledigt?"]),
            ("Rennen und Zeiten", ["Welche Position habe ich?", "In welcher Runde bin ich?",
                                   "Rundenzeiten", "Wie ist mein Delta?", "Wie lange noch?", "Lagebericht"]),
            ("Analyse", ["Wo verliere ich Zeit?", "Wo verliere ich auf den Vordermann?",
                         "Wie konstant bin ich?", "Bauen meine Reifen ab?", "Wie viel fehlt mir auf die Pole?"]),
            ("Strategie", ["Wo komme ich nach dem Stopp raus?", "Wer war schon an der Box?",
                           "Gibt es einen Undercut?", "Soll ich auf Regenreifen wechseln?"]),
            ("Reifen und Bremsen", ["Reifendruck", "Wie warm sind die Reifen?", "Welche Reifen habe ich?",
                                    "Bremsbeläge", "Wie heiß sind die Bremsen?"]),
            ("Wetter und Strecke", ["Wie wird das Wetter?", "Kommt Regen?", "Streckentemperatur",
                                    "Wie ist der Grip?", "Wind"]),
            ("Rennleitung und Auto", ["Habe ich eine Strafe?", "Welche Flagge?", "War die Runde gültig?",
                                      "Habe ich Schaden?", "TC und ABS?", "Wie lange geht mein Stint?"]),
            ("Funk", ["Nochmal", "Funkstille", "Ansagen wieder an", "Was kann ich fragen?", "Danke"]),
            ("Musik", ["Nächstes Lied", "Lied zurück", "Musik aus", "Musik weiter", "Lauter", "Leiser"]),
            ("Mit KI auch frei", ["Soll ich angreifen oder Reifen schonen?", "Wie schaut's mit dem Saft aus?",
                                  "Komm ich an dem vorne noch vorbei?", "Was meinst du, reicht das bis ins Ziel?"]),
        ]
        for i, (titel, saetze) in enumerate(befehle):
            tafel = ctk.CTkFrame(rollen, fg_color=TAFEL, corner_radius=16)
            tafel.grid(row=i // 2, column=i % 2, sticky="nsew", padx=12, pady=12)
            ctk.CTkLabel(tafel, text=titel, text_color=GELB, font=schrift(15, True), anchor="w"
                         ).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 8))
            for j, satz in enumerate(saetze):
                ctk.CTkLabel(tafel, text=f"„{satz}“", text_color=TEXT, font=schrift(14), anchor="w"
                             ).grid(row=j + 1, column=0, sticky="w", padx=22,
                                    pady=(0, 18 if j == len(saetze) - 1 else 3))
        return seite

    # --- Stimmen -----------------------------------------------------------
    @staticmethod
    def _stimmen_text(eintrag):
        _, name, installiert = eintrag
        return name if installiert else name + "  (noch laden)"

    def _stimmen_anzeige(self, stimme_id):
        for eintrag in self.stimmen:
            if eintrag[0] == stimme_id:
                return self._stimmen_text(eintrag)
        windows = [e for e in self.stimmen if e[0].startswith("windows:")]
        return self._stimmen_text(windows[0]) if windows else ""

    def _gewaehlte_stimme(self):
        for eintrag in self.stimmen:
            if self._stimmen_text(eintrag) == self.stimme.get():
                return eintrag
        return None

    def _stimme_gewaehlt(self):
        eintrag = self._gewaehlte_stimme()
        if eintrag and not eintrag[2]:
            self.download_text.configure(text='Diese Stimme muss erst geladen werden. Klick auf "Laden".')
        else:
            self.download_text.configure(text="")
            self._speichern()

    def _stimme_laden(self):
        eintrag = self._gewaehlte_stimme()
        if not eintrag or eintrag[0].startswith("windows:"):
            self.download_text.configure(text="Windows-Stimmen sind schon da, nichts zu laden.")
            return
        if eintrag[2]:
            self.download_text.configure(text="Diese Stimme ist schon geladen.")
            return
        self.download_knopf.configure(state="disabled")
        self.download_text.configure(text="Starte Download ...")
        threading.Thread(target=stimme_einrichten, args=(eintrag[0], self.nachrichten),
                         daemon=True).start()

    def _stimme_testen(self):
        eintrag = self._gewaehlte_stimme()
        if eintrag and not eintrag[2]:
            self.download_text.configure(text='Erst auf "Laden" klicken, dann anhören.')
            return
        self._speichern()
        einstellungen = dict(self.e)

        def testen():
            try:
                if self.test_sprecher:
                    self.test_sprecher.beenden()
                self.test_sprecher, warnung = sprachausgabe_erstellen(einstellungen, self.nachrichten)
                if warnung:
                    self.nachrichten.put(("log", "fehler", warnung))
                self.test_sprecher.sagen("Box, Box. Noch drei Runden Sprit. "
                                         "Abstand zum Vordermann 1,4 Sekunden.", 1)
            except Exception as fehler:
                traceback.print_exc()
                self.nachrichten.put(("log", "fehler", f"Stimme ging nicht: {fehler}"))

        self.download_text.configure(text="Spiele Probe ab ...")
        self.root.after(3000, lambda: self.download_text.configure(text=""))
        threading.Thread(target=testen, daemon=True).start()

    def _aussprache_oeffnen(self):
        aussprache_laden()                   # legt die Datei an, falls sie fehlt
        try:
            os.startfile(AUSSPRACHE_DATEI)
        except Exception as fehler:
            messagebox.showinfo("Aussprache", f"Die Datei liegt hier:\n{AUSSPRACHE_DATEI}\n\n{fehler}")

    # --- KI ----------------------------------------------------------------
    def _gewaehltes_ki_modell(self):
        return next((name for name, text in acc_ki.KI_MODELLE if text == self.ki_modell.get()),
                    acc_ki.KI_MODELLE[0][0])

    def _ki_pruefen(self):
        self.ki_status.configure(text="Prüfe ...", text_color=GEDAEMPFT)
        threading.Thread(target=ki_status_pruefen, args=(self._gewaehltes_ki_modell(), self.nachrichten),
                         daemon=True).start()

    def _ki_laden(self):
        self.ki_lade_knopf.configure(state="disabled")
        self.ki_status.configure(text="Starte Download ...", text_color=GELB)
        threading.Thread(target=ki_modell_laden, args=(self._gewaehltes_ki_modell(), self.nachrichten),
                         daemon=True).start()

    def _ollama_seite(self):
        import webbrowser
        webbrowser.open("https://ollama.com/download")

    # --- Aktionen ----------------------------------------------------------
    def _spaeter_speichern(self):
        if self._speicher_timer:
            self.root.after_cancel(self._speicher_timer)
        self._speicher_timer = self.root.after(500, self._speichern)

    def _speichern(self):
        self._speicher_timer = None
        eintrag = self._gewaehlte_stimme()
        if eintrag and eintrag[2]:
            self.e["stimme"] = eintrag[0]
        mikrofon = self.mikrofon.get()
        self.e.update({
            "tempo": self.tempo.get(),
            "lautstaerke": self.lautstaerke.get(),
            "begruessung": self.begruessung.get(),
            "mikrofon": "" if mikrofon == "Windows-Standard" else mikrofon,
            "modell": self.modell.get().rsplit("(", 1)[-1].rstrip(")"),
            "reserve_runden": float(self.reserve.get().replace(",", ".")),
            "funk": FUNK_STUFEN.index(self.funk.get().lower()),
            "ansagen": {k: v.get() for k, v in self.ansagen_schalter.items()},
            "ki": self.ki_an.get(),
            "ki_modell": self._gewaehltes_ki_modell(),
            "ingenieur_name": self.ingenieur_name.get(),
            "gespraechig": GESPRAECHIG_STUFEN.index(self.gespraechig.get()),
            "fahrer_name": self.fahrer_name.get().strip(),
        })
        einstellungen_speichern(self.e)
        if self.zustand in ("laedt", "bereit"):
            self.einstellung_hinweis.configure(text="Gespeichert. Gilt ab dem nächsten Start.",
                                               text_color=GELB)
        else:
            self.einstellung_hinweis.configure(text="Gespeichert", text_color=GRUEN)
        self.root.after(3000, lambda: self.einstellung_hinweis.configure(
            text="Wird automatisch gespeichert", text_color=GEDAEMPFT))

    def _funktaste_lernen(self):
        if self.zustand != "aus":
            messagebox.showinfo("Funktaste", "Bitte zuerst den Ingenieur stoppen.")
            return
        self.lernt = True
        self.lern_knopf.configure(state="disabled")
        self.start_knopf.configure(state="disabled")
        self.funk_label.configure(text="Jetzt die Taste drücken (15 Sekunden) ...", text_color=GELB)
        threading.Thread(target=funktaste_lernen, args=(self.nachrichten,), daemon=True).start()

    def _verknuepfung(self):
        try:
            ordner = desktop_verknuepfung_erstellen()
            messagebox.showinfo("Verknüpfung", f'"ACC Renningenieur" liegt jetzt auf dem Desktop:\n{ordner}')
        except Exception as fehler:
            messagebox.showerror("Verknüpfung", f"Hat nicht geklappt:\n{fehler}")

    def _start_stopp(self):
        if self.zustand == "aus":
            self._speichern()
            self.ingenieur = Ingenieur(self.nachrichten, self.e)
            self.ingenieur.starten()
            self._zustand_setzen("laedt", "Starte ...")
        elif self.zustand in ("laedt", "bereit"):
            self.ingenieur.anhalten()
            self._zustand_setzen("stoppt", "Stoppe ...")

    def _zustand_setzen(self, zustand, text):
        self.zustand = zustand
        farbe = {"aus": GEDAEMPFT, "laedt": GELB, "bereit": GRUEN, "stoppt": GELB}[zustand]
        self.punkt.configure(text_color=farbe)
        self.status_text.configure(text=text, text_color=TEXT if zustand == "bereit" else GEDAEMPFT)
        if zustand == "aus":
            self.start_knopf.configure(text="Starten", fg_color=GELB, hover_color=GELB_HOVER,
                                       text_color=DUNKEL_TEXT,
                                       state="disabled" if self.lernt else "normal")
            self.funk_anzeige.configure(text="")
            self._cockpit_leer("Starte den Ingenieur unten links.")
        elif zustand == "stoppt":
            self.start_knopf.configure(state="disabled")
        else:
            self.start_knopf.configure(text="Stoppen", fg_color=TAFEL_HELL, hover_color=LINIE,
                                       text_color=TEXT, state="normal")

    # --- Nachrichten vom Hintergrund ---------------------------------------
    def _nachrichten_abholen(self):
        try:
            while True:
                n = self.nachrichten.get_nowait()
                art = n[0]
                if art == "status":
                    if not (self.zustand == "stoppt" and n[1] != "aus"):
                        self._zustand_setzen(n[1], n[2])
                elif art == "log":
                    self._funk_eintrag(n[1], n[2])
                    if n[1] == "fehler":            # auch neben "Anhören" anzeigen
                        self.download_text.configure(text=n[2][:110], text_color=ROT)
                        self.root.after(8000, lambda: self.download_text.configure(text="", text_color=GELB))
                elif art == "protokoll":
                    self.aktuelle_session = n[1]
                    if self.auswertung_quelle.get() == "Aktuelle Session":
                        self._auswertung_zeigen(n[1])
                elif art == "feld":
                    self.feld = n[1]
                    if self.aktuelle_seite == "live":
                        self._live_zeigen()
                elif art == "info":
                    if self.zustand == "bereit":
                        self._cockpit_zeigen(n[1])
                elif art == "funk":
                    self.funk_anzeige.configure(text="Du funkst ..." if n[1] else "", text_color=ROT)
                elif art == "fehler":
                    self._funk_eintrag("fehler", n[1])
                    messagebox.showwarning("Renningenieur", n[1])
                elif art == "download":
                    self.download_text.configure(text=n[1])
                elif art == "download_fertig":
                    self.download_knopf.configure(state="normal")
                    if n[2]:
                        self.download_text.configure(text="")
                        messagebox.showerror("Stimme laden", f"Hat nicht geklappt:\n{n[2]}")
                    else:
                        self.stimmen = stimmen_liste()
                        self.stimm_auswahl.configure(values=[self._stimmen_text(e) for e in self.stimmen])
                        self.stimme.set(self._stimmen_anzeige(n[1]))
                        self._speichern()
                        self.download_text.configure(text='Fertig! Klick auf "Anhören".')
                elif art == "ki_status":
                    farbe = {"rot": ROT, "gelb": GELB, "gruen": GRUEN}[n[2]]
                    self.ki_status.configure(text=n[1], text_color=farbe)
                elif art == "ki_fertig":
                    self.ki_lade_knopf.configure(state="normal")
                    if n[1]:
                        self.ki_status.configure(text="Laden fehlgeschlagen", text_color=ROT)
                        messagebox.showerror("KI-Modell", f"Hat nicht geklappt:\n{n[1]}")
                    else:
                        self.ki_an.set(True)
                        self._speichern()
                        self.ki_status.configure(text="Bereit", text_color=GRUEN)
                elif art == "denkt":
                    self.funk_anzeige.configure(text="Ingenieur überlegt ..." if n[1] else "",
                                                text_color=GELB)
                elif art == "lernen_fertig":
                    self.lernt = False
                    self.lern_knopf.configure(state="normal")
                    if self.zustand == "aus":
                        self.start_knopf.configure(state="normal")
                    if n[2]:
                        self.funk_label.configure(text=acc_funktaste.beschreibung(), text_color=TEXT)
                        messagebox.showwarning("Funktaste", n[2])
                    else:
                        self.funk_label.configure(text=n[1], text_color=GRUEN)
        except queue.Empty:
            pass
        self.root.after(100, self._nachrichten_abholen)

    def _schliessen(self):
        if self.ingenieur and self.zustand != "aus":
            self.ingenieur.anhalten()
            self.root.after(600, self.root.destroy)    # kurz Zeit zum Abmelden geben
        else:
            self.root.destroy()


def main():
    global SCHRIFT, SCHRIFT_ENG
    # Neues Fenster im Glas-Design. Klappt das nicht (oder mit "--alt" gestartet), kommt das alte.
    if "--alt" not in sys.argv:
        try:
            import acc_fenster
            if acc_fenster.main(sys.modules[__name__]):
                return
        except Exception:
            traceback.print_exc()
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    # Bahnschrift ist in Windows eingebaut und sieht aus wie die DIN-Schrift an Rennstrecken
    from tkinter import font as tkfont
    familien = set(tkfont.families(root))
    if "Bahnschrift" in familien:
        SCHRIFT = "Bahnschrift"
        SCHRIFT_ENG = "Bahnschrift SemiCondensed" if "Bahnschrift SemiCondensed" in familien else "Bahnschrift"
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
