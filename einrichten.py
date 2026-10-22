# einrichten.py
# Wird vom Setup (Inno Setup) nach dem Kopieren der Dateien aufgerufen, einmal pro Schritt:
#   python einrichten.py pakete                 Zusatzpakete installieren (pip)
#   python einrichten.py acc                    ACC so einstellen, dass es Daten schickt (broadcasting.json)
#   python einrichten.py einstellungen ...      Sprache, KI, Farbthema in einstellungen.json eintragen
#   python einrichten.py stimme --sprache de    Die Stimme des Ingenieurs laden (einmalig)
#   python einrichten.py ollama                 Nur bei lokaler KI: Ollama und das Modell laden
# Alles wird in setup-protokoll.txt im Programmordner mitgeschrieben.
# Rückgabe: 0 = gut, 1 = Fehler (das Setup zeigt dann einen Hinweis), 2 = Warnung (Setup läuft weiter)

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ORDNER = os.path.dirname(os.path.abspath(__file__))
PROTOKOLL = os.path.join(ORDNER, "setup-protokoll.txt")
PAKETE = ["numpy", "sounddevice", "faster-whisper", "pywin32", "customtkinter", "pywebview", "edge-tts", "piper-tts"]
THEMEN = ["kupfer", "gold", "petrol", "eis", "silber", "klassik", "strecke", "nacht"]
STIMME = {"de": "de_DE-thorsten-high", "en": "en_GB-northern_english_male-medium"}
OHNE_FENSTER = 0x08000000 if os.name == "nt" else 0      # CREATE_NO_WINDOW


def log(text):
    zeile = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {text}"
    print(zeile, flush=True)
    try:
        with open(PROTOKOLL, "a", encoding="utf-8") as datei:
            datei.write(zeile + "\n")
    except OSError:
        pass


def ausfuehren(befehl, zeitlimit=None):
    log("> " + " ".join(befehl))
    prozess = subprocess.Popen(befehl, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               encoding="utf-8", errors="replace", creationflags=OHNE_FENSTER)
    for zeile in prozess.stdout:
        if zeile.strip():
            log("  " + zeile.rstrip())
    return prozess.wait(timeout=zeitlimit)


# ---------------------------------------------------------------------------
def pip_da():
    try:
        return subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True,
                              creationflags=OHNE_FENSTER).returncode == 0
    except OSError:
        return False


def pakete():
    if not pip_da():
        log("pip fehlt, wird nachgerüstet ...")
        ausfuehren([sys.executable, "-m", "ensurepip", "--upgrade", "--default-pip"])
    if not pip_da():
        try:
            ziel = os.path.join(tempfile.gettempdir(), "pitvoice-get-pip.py")
            urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", ziel)
            ausfuehren([sys.executable, ziel, "--disable-pip-version-check"])
            os.remove(ziel)
        except Exception as fehler:
            log(f"get-pip: {fehler}")
    if not pip_da():
        log("FEHLER: pip konnte nicht eingerichtet werden.")
        return 1
    code = ausfuehren([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                       "--progress-bar", "off"] + PAKETE)
    if code != 0:
        log("FEHLER: Die Zusatzpakete konnten nicht installiert werden.")
        return 1
    log("OK: Alle Pakete sind da.")
    return 0


# ---------------------------------------------------------------------------
def dokumente():
    """Der echte Dokumente-Ordner (auch wenn er zum Beispiel in OneDrive liegt)."""
    if os.name == "nt":
        try:
            import ctypes
            puffer = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, puffer) == 0 and puffer.value:
                return puffer.value
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def json_lesen(pfad):
    roh = open(pfad, "rb").read()
    if roh[:2] == b"\xff\xfe":
        return roh[2:].decode("utf-16-le"), "utf16", True
    if len(roh) > 1 and roh[1:2] == b"\x00":
        return roh.decode("utf-16-le"), "utf16", False
    return roh.decode("utf-8", errors="replace").lstrip("﻿"), "utf8", False


def json_schreiben(pfad, text, art, bom):
    daten = text.encode("utf-16-le") if art == "utf16" else text.encode("utf-8")
    if art == "utf16" and bom:
        daten = b"\xff\xfe" + daten
    with open(pfad, "wb") as datei:
        datei.write(daten)


def acc():
    ordner = os.path.join(dokumente(), "Assetto Corsa Competizione", "Config")
    datei = os.path.join(ordner, "broadcasting.json")
    port, passwort = 9000, "asd"
    if os.path.exists(datei):
        text, art, bom = json_lesen(datei)
        try:
            daten = json.loads(text)
        except ValueError:
            daten = {}
        if daten.get("updListenerPort") == port and daten.get("connectionPassword") == passwort:
            log("OK: ACC ist schon richtig eingestellt.")
            return 0
        shutil.copyfile(datei, datei + ".vor-renningenieur")
        neu = json.dumps({"updListenerPort": port, "connectionPassword": passwort,
                          "commandPassword": str(daten.get("commandPassword") or "")}, indent=4) + "\r\n"
        json_schreiben(datei, neu.replace("\n", "\r\n").replace("\r\r\n", "\r\n"), art, bom)
        log("OK: ACC sendet jetzt Daten an PitVoice AI (Port 9000). Sicherung: broadcasting.json.vor-renningenieur")
        return 0
    if os.path.isdir(ordner):
        neu = json.dumps({"updListenerPort": port, "connectionPassword": passwort, "commandPassword": ""}, indent=4)
        json_schreiben(datei, neu.replace("\n", "\r\n") + "\r\n", "utf16", True)
        log("OK: Einstellungsdatei für ACC angelegt.")
        return 0
    log("WARNUNG: ACC-Einstellungen nicht gefunden. ACC einmal starten, beenden und das Setup erneut ausführen.")
    return 2


# ---------------------------------------------------------------------------
def einstellungen_laden():
    pfad = os.path.join(ORDNER, "einstellungen.json")
    try:
        with open(pfad, encoding="utf-8") as datei:
            return json.load(datei)
    except (OSError, ValueError):
        return {}


def einstellungen_speichern(e):
    with open(os.path.join(ORDNER, "einstellungen.json"), "w", encoding="utf-8") as datei:
        json.dump(e, datei, ensure_ascii=False, indent=2)


def einstellungen(a):
    e = einstellungen_laden()
    e["sprache"] = "en" if a.sprache == "en" else "de"
    if a.thema in THEMEN:
        e["thema"] = a.thema
    schluessel = ""
    if a.schluessel_datei and os.path.exists(a.schluessel_datei):
        try:
            with open(a.schluessel_datei, encoding="utf-8-sig") as datei:
                schluessel = datei.read().strip()
        finally:
            try:
                os.remove(a.schluessel_datei)
            except OSError:
                pass
    if a.ki == "lokal":
        e["ki"] = True
        e["ki_anbieter"] = "lokal"
        e["erkennung_online"] = False
        e.setdefault("ki_modell", "gemma3:4b")
    else:
        e["ki_anbieter"] = "groq"
        e["erkennung_online"] = a.erkennung == "1"
        if schluessel:
            e["schluessel_groq"] = schluessel
            e["ki"] = True
            log("OK: Online-KI über Groq ist eingerichtet.")
        else:
            log("Hinweis: Kein Schlüssel eingetragen, geht später im Programm unter Einstellungen > KI.")
    einstellungen_speichern(e)
    log("OK: Einstellungen gespeichert.")
    return 0


# ---------------------------------------------------------------------------
def stimme(a):
    sys.path.insert(0, ORDNER)
    name = STIMME["en" if a.sprache == "en" else "de"]
    e = einstellungen_laden()
    try:
        import acc_stimme
        if not acc_stimme.piper_installiert(name):
            log(f"Lade die Stimme {name} (einmalig, etwa 100 MB) ...")
            acc_stimme.piper_herunterladen(name)
        log("OK: Stimme ist da.")
        ergebnis = 0
    except Exception as fehler:
        log(f"WARNUNG: Die Stimme konnte nicht geladen werden ({fehler}). Geht später im Programm.")
        ergebnis = 2
    if not e.get("stimme") or str(e.get("stimme")).startswith("windows:"):
        e["stimme"] = "piper:" + name
        einstellungen_speichern(e)
    return ergebnis


# ---------------------------------------------------------------------------
def ollama():
    sys.path.insert(0, ORDNER)
    pfad = shutil.which("ollama") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
    if not os.path.exists(pfad) and shutil.which("winget"):
        log("Ollama wird installiert (kostenlos, ollama.com) ...")
        ausfuehren(["winget", "install", "-e", "--id", "Ollama.Ollama", "--silent", "--accept-package-agreements",
                    "--accept-source-agreements", "--disable-interactivity"])
    if not os.path.exists(pfad):
        log("WARNUNG: Ollama konnte nicht installiert werden. Bitte von ollama.com laden und das Modell im Programm laden.")
        return 2

    def laeuft():
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2).read()
            return True
        except Exception:
            return False

    if not laeuft():
        subprocess.Popen([pfad, "serve"], creationflags=OHNE_FENSTER)
        for _ in range(30):
            time.sleep(1)
            if laeuft():
                break
    if not laeuft():
        log("WARNUNG: Ollama startet nicht. Das Modell kannst du später im Programm laden.")
        return 2
    modell = einstellungen_laden().get("ki_modell") or "gemma3:4b"
    try:
        import acc_ki
        log(f"Lade das KI-Modell {modell} (etwa 3 GB, einmalig) ...")
        acc_ki.modell_laden(modell)
        log("OK: KI-Modell ist geladen.")
        return 0
    except Exception as fehler:
        log(f"WARNUNG: Das KI-Modell konnte nicht geladen werden ({fehler}). Geht später im Programm.")
        return 2


def main():
    teil = argparse.ArgumentParser()
    teil.add_argument("schritt", choices=["pakete", "acc", "einstellungen", "stimme", "ollama"])
    teil.add_argument("--sprache", default="de")
    teil.add_argument("--ki", default="online")
    teil.add_argument("--erkennung", default="1")
    teil.add_argument("--thema", default="")
    teil.add_argument("--schluessel-datei", dest="schluessel_datei", default="")
    a = teil.parse_args()
    log(f"--- Schritt: {a.schritt} (Python {sys.version.split()[0]})")
    try:
        if a.schritt == "pakete":
            return pakete()
        if a.schritt == "acc":
            return acc()
        if a.schritt == "einstellungen":
            return einstellungen(a)
        if a.schritt == "stimme":
            return stimme(a)
        return ollama()
    except Exception as fehler:
        log(f"FEHLER: {type(fehler).__name__}: {fehler}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
