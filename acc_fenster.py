# acc_fenster.py
# Das neue Programmfenster im Glas-Design.
# Die Oberfläche ist eine kleine Webseite (Ordner "oberflaeche"), die in einem eigenen
# Fenster läuft. Alles bleibt auf deinem PC: Windows bringt das nötige Bauteil
# (WebView2, das gleiche wie im Edge-Browser) schon mit, ins Internet geht nichts.
#
# Dieses Programm ist die Brücke: Die Webseite fragt hier nach Daten und schickt
# Knopfdrücke, und hier läuft im Hintergrund der Renningenieur (aus acc_app.py).
#
# Gestartet wird es automatisch über acc_app.py (Desktop-Verknüpfung).

import json
import os
import queue
import sys
import threading
import time
import traceback
import acc_sprache
from acc_sprache import L

ORDNER = os.path.dirname(os.path.abspath(__file__))
OBERFLAECHE = os.path.join(ORDNER, "oberflaeche", "index.html")

BEFEHLE_BEISPIELE = L([
    ("Auf der Strecke", ["Wer ist auf der Strecke vor mir?", "Wer fährt auf der Strecke hinter mir?",
                         "Wer ist vor mir und wie viel Abstand habe ich?"]),
    ("Abstände und Gegner", ["Abstand zum Vordermann", "Wer ist hinter mir?", "Abstand zu P3",
                             "Abstand zum Führenden", "Bin ich schneller als der Vordermann?",
                             "Wer hat die schnellste Runde?"]),
    ("Sprit und Boxenstopp", ["Wie viel Sprit habe ich?", "Wie viel verbrauche ich?",
                              "Wann muss ich an die Box?", "Ich bin in der Box",
                              "Schaffe ich es ohne Stopp?", "Pflichtstopp erledigt?"]),
    ("Rennen und Zeiten", ["Welche Position habe ich?", "In welcher Runde bin ich?",
                           "Rundenzeiten", "Wie ist mein Delta?", "Wie lange noch?", "Lagebericht"]),
    ("Analyse", ["Wo verliere ich Zeit?", "Wo verliere ich auf den Vordermann?",
                 "Wie konstant bin ich?", "Bauen meine Reifen ab?", "Wie viel fehlt mir auf die Pole?"]),
    ("Strategie", ["Wo komme ich nach dem Stopp raus?", "Wer war schon an der Box?",
                   "Gibt es einen Undercut?", "Soll ich auf Regenreifen wechseln?",
                   "Wie viel Sprit für 30 Minuten?", "Soll ich den Reifendruck anpassen?"]),
    ("Reifen und Bremsen", ["Reifendruck", "Wie warm sind die Reifen?", "Welche Reifen habe ich?",
                            "Bremsbeläge", "Wie heiß sind die Bremsen?"]),
    ("Wetter und Strecke", ["Wie wird das Wetter?", "Kommt Regen?", "Streckentemperatur",
                            "Wie ist der Grip?", "Wind"]),
    ("Rennleitung und Auto", ["Habe ich eine Strafe?", "Welche Flagge?", "War die Runde gültig?",
                              "Habe ich Schaden?", "TC und ABS?", "Wie lange geht mein Stint?"]),
    ("Funk", ["Nochmal", "Funkstille", "Ansagen wieder an", "Was kann ich fragen?", "Danke"]),
    ("Musik", ["Nächstes Lied", "Lied zurück", "Musik aus", "Musik weiter", "Lauter", "Leiser"]),
    ("Mit KI auch frei", ["Soll ich angreifen oder Reifen schonen?", "Wie schaut's mit dem Saft aus?",
                          "Komm ich an dem vorne noch vorbei?", "Ich hab mich gedreht, was jetzt?"]),
], [
    ("On track", ["Who is ahead of me on track?", "Who is behind me on track?",
                  "Who is ahead of me and what is the gap?"]),
    ("Gaps and opponents", ["Gap to the car ahead", "Who is behind me?", "Gap to P3",
                            "Gap to the leader", "Am I faster than the car ahead?",
                            "Who has the fastest lap?"]),
    ("Fuel and pit stop", ["How much fuel do I have?", "What is my consumption?",
                           "When do I need to pit?", "I'm in the pits",
                           "Can I make it without a stop?", "Mandatory stop done?"]),
    ("Race and times", ["What position am I?", "What lap am I on?",
                        "Lap times", "What is my delta?", "How long to go?", "Situation report"]),
    ("Analysis", ["Where am I losing time?", "Where am I losing to the car ahead?",
                  "How consistent am I?", "Are my tyres degrading?", "How far am I off pole?"]),
    ("Strategy", ["Where will I rejoin after the stop?", "Who has already pitted?",
                  "Is there an undercut?", "Should I switch to wet tyres?",
                  "How much fuel for 30 minutes?", "Should I adjust the tyre pressures?"]),
    ("Tyres and brakes", ["Tyre pressures", "How warm are the tyres?", "Which tyres am I on?",
                          "Brake pads", "How hot are the brakes?"]),
    ("Weather and track", ["What is the weather doing?", "Is rain coming?", "Track temperature",
                           "How is the grip?", "Wind"]),
    ("Race control and car", ["Do I have a penalty?", "Which flag?", "Was the lap valid?",
                              "Do I have damage?", "TC and ABS?", "How long is my stint?"]),
    ("Radio", ["Say again", "Radio silence", "Announcements on", "What can I ask?", "Thanks"]),
    ("Music", ["Next song", "Previous song", "Music off", "Music on", "Louder", "Quieter"]),
    ("Free speech with AI", ["Should I attack or save the tyres?", "How are we looking on fuel?",
                             "Can I still get past the guy ahead?", "I spun, what now?"]),
])


def _sicher(funktion):
    """Fehler in einer Brücken-Funktion landen im Log statt die Oberfläche einzufrieren."""
    def huelle(*argumente, **optionen):
        try:
            return funktion(*argumente, **optionen)
        except Exception as fehler:
            traceback.print_exc()
            return {"fehler": str(fehler)}
    huelle.__name__ = funktion.__name__
    return huelle


class Bruecke:
    """Alles, was die Webseite aufrufen kann (window.pywebview.api.<name>)."""

    def __init__(self, kern):
        self._kern = kern
        self._e = kern.einstellungen_laden()
        self._nachrichten = queue.Queue()
        self._ingenieur = None
        self._zustand = "aus"
        self._test_sprecher = None
        self._feld = {"autos": [], "karte": []}
        self._sperre = threading.Lock()
        # Für Handy-Anzeige und Overlay: das Neueste merken
        self._info = {}
        self._feld_leicht = {"autos": [], "karte": []}
        self._funk = []
        self._handy = None
        self._overlay = None
        self._webview = None

    # --- Start: alles, was die Seite einmal braucht ---------------------------
    @_sicher
    def anfang(self):
        k = self._kern
        import acc_funktaste
        import acc_ki
        from acc_ansagen import ANSAGEN, GESPRAECHIG_STUFEN
        from acc_stimme import FUNK_STUFEN, stimmen_liste
        threading.Thread(target=k.ki_status_pruefen, args=(self._e.get("ki_modell"), self._nachrichten, self._e),
                         daemon=True).start()

        def update_suchen():
            info = k.update_pruefen() if hasattr(k, "update_pruefen") else None
            if info:
                self._update_seite = info.get("seite", "")
                self._nachrichten.put(("update", info))
        threading.Thread(target=update_suchen, daemon=True).start()
        return {
            "e": self._e,
            "zustand": self._zustand,
            "ansagen": [[s, t] for s, t, _ in ANSAGEN],
            "gespraechig": GESPRAECHIG_STUFEN,
            "stimmen": [list(s) for s in stimmen_liste()],
            "mikrofone": k.mikrofone_auflisten(),
            "modelle": [[n, t] for n, t in k.MODELLE],
            "ki_modelle": [[n, t] for n, t in acc_ki.KI_MODELLE],
            "funk_stufen": L([s.capitalize() for s in FUNK_STUFEN], ["Off", "Light", "Medium", "Strong"]),
            "reserven": k.RESERVEN,
            "funktaste": acc_funktaste.beschreibung(),
            "ingenieur_namen": k.INGENIEUR_NAMEN,
            "befehle": BEFEHLE_BEISPIELE,
            "sessions": self.sessions(),
            "neural_hinweis": __import__("acc_stimme").NEURAL_HINWEIS,
            "produkt": getattr(self._kern, "PRODUKT", ""),
            "newsletter": getattr(self._kern, "NEWSLETTER_ADRESSE", ""),
            "spenden": getattr(self._kern, "SPENDEN_ADRESSE", ""),
            "version": getattr(self._kern, "VERSION", ""),
            "sprache": acc_sprache.SPRACHE,          # die Sprache, mit der das Programm gerade läuft
            "sprachen": [[k, v] for k, v in acc_sprache.SPRACHEN.items()],
        }

    @_sicher
    def lizenzen_oeffnen(self):
        pfad = os.path.join(ORDNER, "DRITTANBIETER.txt")
        if os.path.exists(pfad):
            os.startfile(pfad)
        return True

    @_sicher
    def fehler_melden(self):
        """Schreibt einen Fehlerbericht (Version, Windows, letzte Protokollzeilen, ohne Schlüssel),
        zeigt ihn im Explorer an und öffnet eine fertige E-Mail an info@pitvoice.com."""
        import platform
        import re
        import subprocess
        import urllib.parse
        import webbrowser

        def schwaerzen(text):
            # API-Schlüssel und ähnliches nie mitschicken
            text = re.sub(r"\b(gsk_|AIza|sk-)[A-Za-z0-9_\-]{8,}", r"\1***", text)
            return re.sub(r'("(?:\w*schluessel\w*|\w*key\w*)"\s*:\s*")[^"]*(")', r"\1***\2", text, flags=re.I)

        version = f"{getattr(self._kern, 'PRODUKT', 'PitVoice AI')} {getattr(self._kern, 'VERSION', '')}".strip()
        system = f"{platform.system()} {platform.release()} ({platform.version()}), Python {platform.python_version()}"
        try:
            with open(getattr(self._kern, "LOGDATEI", os.path.join(ORDNER, "renningenieur_log.txt")),
                      encoding="utf-8", errors="replace") as datei:
                zeilen = datei.read().splitlines()[-400:]
        except OSError:
            zeilen = []
        einstellungen = {k: v for k, v in self._e.items()
                         if "schluessel" not in k.lower() and "key" not in k.lower()} if isinstance(self._e, dict) else {}
        bericht = "\n".join([
            "PitVoice AI - Fehlerbericht", "=" * 27,
            f"Version: {version}", f"System:  {system}", "",
            "Einstellungen (ohne Schlüssel):", schwaerzen(json.dumps(einstellungen, ensure_ascii=False, indent=1, default=str)), "",
            "Letzte Zeilen aus dem Protokoll:", "-" * 32, schwaerzen("\n".join(zeilen)),
        ])
        pfad = os.path.join(ORDNER, "PitVoice-Fehlerbericht.txt")
        with open(pfad, "w", encoding="utf-8") as datei:
            datei.write(bericht)
        try:
            subprocess.Popen(["explorer", "/select,", pfad])
        except OSError:
            pass
        englisch = L("de", "en") == "en"
        text = L("Hallo,\n\nwas ist passiert? (bitte kurz beschreiben)\n\n\n"
                 "Wann? (z. B. beim Start, im Rennen, beim Fragen)\n\n\n"
                 "Bitte die Datei PitVoice-Fehlerbericht.txt anhängen. Der Ordner hat sich gerade geöffnet.\n\n",
                 "Hi,\n\nwhat happened? (please describe briefly)\n\n\n"
                 "When? (e.g. on start, in the race, when asking)\n\n\n"
                 "Please attach the file PitVoice-Fehlerbericht.txt. The folder has just opened.\n\n")
        text += f"{version} · {system}\n\n" + schwaerzen("\n".join(zeilen[-12:]))[-900:]
        betreff = f"PitVoice AI: {'Bug report' if englisch else 'Fehlerbericht'} ({version})"
        webbrowser.open("mailto:info@pitvoice.com?subject=" + urllib.parse.quote(betreff) + "&body=" + urllib.parse.quote(text))
        return {"datei": pfad}

    @_sicher
    def neustart(self):
        """Startet das Programm neu (zum Beispiel nach dem Wechsel der Sprache)."""
        import subprocess
        self._kern.einstellungen_speichern(self._e)
        programm = sys.executable
        if programm.lower().endswith("python.exe"):
            fenster_los = programm[:-len("python.exe")] + "pythonw.exe"
            if os.path.exists(fenster_los):
                programm = fenster_los
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        env = dict(os.environ)
        env.pop("ACC_SPRACHE", None)
        subprocess.Popen([programm, os.path.join(ORDNER, "acc_app.py")], cwd=ORDNER, creationflags=flags, env=env)

        def schliessen():
            time.sleep(0.3)
            try:
                for fenster in list(self._webview.windows):
                    fenster.destroy()
            except Exception:
                os._exit(0)
        threading.Thread(target=schliessen, daemon=True).start()
        return True

    # --- Einstellungen ----------------------------------------------------------
    @_sicher
    def speichern(self, teil):
        self._e.update(teil or {})
        self._kern.einstellungen_speichern(self._e)
        return {"gilt_ab_start": self._zustand in ("laedt", "bereit")}

    # --- Ingenieur starten und stoppen ------------------------------------------
    @_sicher
    def start_stopp(self):
        if self._zustand == "aus":
            self._ingenieur = self._kern.Ingenieur(self._nachrichten, self._e)
            self._ingenieur.starten()
            self._zustand = "laedt"
            self._nachrichten.put(("status", "laedt", L("Starte ...", "Starting ...")))
        elif self._zustand in ("laedt", "bereit"):
            self._ingenieur.anhalten()
            self._zustand = "stoppt"
            self._nachrichten.put(("status", "stoppt", L("Stoppe ...", "Stopping ...")))
        return self._zustand

    # --- Overlay über ACC und Anzeige auf dem Handy ---------------------------------
    def _anzeige_daten(self):
        return {"zustand": self._zustand, "info": self._info, "feld": self._feld_leicht,
                "funk": self._funk, "ingenieur": self._e.get("ingenieur_name") or L("Ingenieur", "Engineer"),
                "spiegeln": bool(self._e.get("karte_spiegeln")), "sprache": acc_sprache.SPRACHE,
                "thema": self._e.get("thema", "kupfer")}

    @_sicher
    def overlay_daten(self):
        return self._anzeige_daten()

    @_sicher
    def overlay(self, an):
        """Kleines Fenster, das immer über ACC liegt (ACC im Fenster- oder rahmenlosen Modus)."""
        self._e["overlay"] = bool(an)
        self._kern.einstellungen_speichern(self._e)
        if an and self._overlay is None and self._webview is not None:
            pfad = os.path.join(ORDNER, "oberflaeche", "overlay.html")
            self._overlay = self._webview.create_window(
                "PitVoice AI Overlay", pfad, js_api=self, width=340, height=150, x=40, y=40,
                on_top=True, frameless=True, easy_drag=True, background_color="#0B0B0E")
            self._overlay.events.closed += self._overlay_zu
        elif not an and self._overlay is not None:
            fenster, self._overlay = self._overlay, None
            fenster.destroy()
        return bool(self._overlay)

    def _overlay_zu(self):
        self._overlay = None

    @_sicher
    def handy(self, an):
        """Anzeige fürs Handy oder Tablet im WLAN (nur lesen, keine Steuerung)."""
        self._e["handy"] = bool(an)
        self._kern.einstellungen_speichern(self._e)
        if an and self._handy is None:
            self._handy = HandyServer(self._anzeige_daten)
            self._handy.start()
        elif not an and self._handy is not None:
            self._handy.stoppen()
            self._handy = None
        return {"an": self._handy is not None, "adresse": self._handy.adresse if self._handy else ""}

    @_sicher
    def fortschritt(self):
        import acc_gedaechtnis
        return acc_gedaechtnis.alles_laden()

    def beenden(self):
        if self._handy is not None:
            self._handy.stoppen()
        if self._overlay is not None:
            try:
                self._overlay.destroy()
            except Exception:
                pass
        if self._ingenieur and self._zustand != "aus":
            self._ingenieur.anhalten()
            time.sleep(0.5)                       # kurz Zeit zum Abmelden geben
        if self._test_sprecher:
            try:
                self._test_sprecher.beenden()
            except Exception:
                pass

    # --- Nachrichten an die Seite --------------------------------------------------
    @_sicher
    def abholen(self):
        """Die Seite holt hier mehrmals pro Sekunde alles Neue ab."""
        ausgabe = []
        while True:
            try:
                n = self._nachrichten.get_nowait()
            except queue.Empty:
                break
            art = n[0]
            if art == "status":
                if self._zustand == "stoppt" and n[1] != "aus":
                    continue
                self._zustand = n[1]
            elif art == "feld":
                # Die Rundenlisten aller Autos bleiben hier, die Seite holt sie nur für den Fokus
                with self._sperre:
                    self._feld = n[1]
                leicht = {"karte": n[1].get("karte", []),
                          "autos": [{k: v for k, v in a.items() if k != "runden"} | {"rundenzahl": len(a["runden"])}
                                    for a in n[1].get("autos", [])]}
                self._feld_leicht = leicht
                ausgabe.append(["feld", leicht])
                continue
            elif art == "info":
                self._info = n[1]
            elif art == "log" and n[1] in ("du", "ingenieur", "ansage"):
                self._funk = (self._funk + [[n[1], n[2]]])[-4:]
            elif art == "ki_fertig" and not n[1]:
                self._e["ki"] = True
                self._kern.einstellungen_speichern(self._e)
            ausgabe.append(list(n))
        return ausgabe

    @_sicher
    def runden(self, index):
        with self._sperre:
            for auto in self._feld.get("autos", []):
                if auto["index"] == index:
                    return auto.get("runden", [])
        return []

    @_sicher
    def telemetrie(self):
        """Die Telemetrie der laufenden Session (alle aufgezeichneten Runden)."""
        stand = getattr(self._ingenieur, "stand", None) if self._ingenieur else None
        if stand is None:
            return None
        with stand.sperre:
            return stand.telemetrie.export(stand.acc.streckenlaenge_m)

    @_sicher
    def kurven(self, runde, beste, laenge):
        """Vergleich zweier Runden Kurve für Kurve (für die Telemetrie-Ansicht)."""
        import acc_telemetrie
        if not runde or not beste:
            return []
        ergebnisse = acc_telemetrie.vergleichen(runde, beste, laenge)
        for e in ergebnisse:
            e["grund"] = acc_telemetrie.grund_text(e)
        return ergebnisse

    # --- Stimmen ---------------------------------------------------------------------
    @_sicher
    def stimmen(self):
        from acc_stimme import stimmen_liste
        return [list(s) for s in stimmen_liste()]

    @_sicher
    def stimme_laden(self, stimme_id):
        threading.Thread(target=self._kern.stimme_einrichten, args=(stimme_id, self._nachrichten),
                         daemon=True).start()
        return True

    @_sicher
    def stimme_testen(self):
        einstellungen = dict(self._e)

        def testen():
            try:
                if self._test_sprecher:
                    self._test_sprecher.beenden()
                self._test_sprecher, warnung = self._kern.sprachausgabe_erstellen(einstellungen, self._nachrichten)
                if warnung:
                    self._nachrichten.put(("log", "fehler", warnung))
                name = einstellungen.get("fahrer_name") or ""
                self._test_sprecher.sagen(L(f"Box, Box{', ' + name if name else ''}. Noch drei Runden Sprit. "
                                          "Der Abstand zum Vordermann beträgt 1,4 Sekunden.", f"Box, box{', ' + name if name else ''}. Three laps of fuel left. "
                                          "The gap to the car ahead is 1.4 seconds."), 1)
            except Exception as fehler:
                traceback.print_exc()
                self._nachrichten.put(("log", "fehler", L(f"Stimme ging nicht: {fehler}", f"Voice didn't work: {fehler}")))

        threading.Thread(target=testen, daemon=True).start()
        return True

    @_sicher
    def aussprache_oeffnen(self):
        from acc_stimme import AUSSPRACHE_DATEI, aussprache_laden
        aussprache_laden()
        os.startfile(AUSSPRACHE_DATEI)
        return True

    # --- Funktaste, KI, Programm --------------------------------------------------------
    @_sicher
    def funktaste_lernen(self):
        if self._zustand != "aus":
            return {"fehler": L("Bitte zuerst den Ingenieur stoppen.", "Please stop the engineer first.")}
        threading.Thread(target=self._kern.funktaste_lernen, args=(self._nachrichten,), daemon=True).start()
        return True

    @_sicher
    def ki_pruefen(self):
        threading.Thread(target=self._kern.ki_status_pruefen,
                         args=(self._e.get("ki_modell"), self._nachrichten, dict(self._e)), daemon=True).start()
        return True

    @_sicher
    def ki_laden(self):
        threading.Thread(target=self._kern.ki_modell_laden, args=(self._e.get("ki_modell"), self._nachrichten),
                         daemon=True).start()
        return True

    @_sicher
    def webseite(self, adresse):
        import webbrowser
        if adresse in ("https://ollama.com/download", "https://aistudio.google.com/apikey",
                       "https://console.groq.com/keys", "https://pitvoice.com") or (adresse and adresse == getattr(self, "_update_seite", None)) \
                or (adresse and adresse.startswith("https://") and adresse in (getattr(self._kern, "NEWSLETTER_ADRESSE", ""),
                                                                             getattr(self._kern, "SPENDEN_ADRESSE", ""))):
            webbrowser.open(adresse)
        return True

    @_sicher
    def verknuepfung(self):
        return {"ordner": self._kern.desktop_verknuepfung_erstellen()}

    # --- Auswertung ---------------------------------------------------------------------
    @_sicher
    def sessions(self):
        import acc_protokoll
        try:
            dateien = sorted((d for d in os.listdir(acc_protokoll.RENNEN_ORDNER) if d.endswith(".json")),
                             reverse=True)[:60]
        except OSError:
            dateien = []
        return dateien

    @_sicher
    def session_laden(self, name):
        import acc_protokoll
        if os.path.basename(name) != name or not name.endswith(".json"):
            return None
        with open(os.path.join(acc_protokoll.RENNEN_ORDNER, name), encoding="utf-8") as datei:
            return json.load(datei)

    @_sicher
    def ordner_oeffnen(self):
        import acc_protokoll
        os.makedirs(acc_protokoll.RENNEN_ORDNER, exist_ok=True)
        os.startfile(acc_protokoll.RENNEN_ORDNER)
        return True


# ---------------------------------------------------------------------------
# Kleiner Webserver fürs Handy: liefert eine Seite und die aktuellen Daten.
# Nur im eigenen WLAN erreichbar, nur zum Anschauen (keine Steuerung).
# ---------------------------------------------------------------------------
HANDY_PORT = 8765


def eigene_adresse():
    """Die Adresse dieses PCs im WLAN/Heimnetz, z. B. 192.168.178.20."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))           # schickt nichts, findet nur die passende Netzwerkkarte
        adresse = s.getsockname()[0]
        s.close()
        return adresse
    except OSError:
        return "127.0.0.1"


class HandyServer(threading.Thread):
    def __init__(self, daten_holen):
        super().__init__(daemon=True)
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        daten = daten_holen
        seite = os.path.join(ORDNER, "oberflaeche", "handy.html")

        class Antwort(BaseHTTPRequestHandler):
            def log_message(self, *argumente):
                pass

            def do_GET(self):
                if self.path.startswith("/daten"):
                    inhalt = json.dumps(daten(), ensure_ascii=False).encode("utf-8")
                    art = "application/json; charset=utf-8"
                elif self.path in ("/", "/index.html"):
                    with open(seite, "rb") as datei:
                        inhalt = datei.read()
                    art = "text/html; charset=utf-8"
                elif self.path in ("/sprache.js", "/themen.js"):
                    with open(os.path.join(os.path.dirname(seite), self.path.lstrip("/")), "rb") as datei:
                        inhalt = datei.read()
                    art = "text/javascript; charset=utf-8"
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", art)
                self.send_header("Content-Length", str(len(inhalt)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(inhalt)

        self.server = ThreadingHTTPServer(("0.0.0.0", HANDY_PORT), Antwort)
        self.adresse = f"http://{eigene_adresse()}:{HANDY_PORT}"

    def run(self):
        self.server.serve_forever(poll_interval=0.5)

    def stoppen(self):
        self.server.shutdown()
        self.server.server_close()


# ---------------------------------------------------------------------------
# pywebview holen (einmalig installieren, falls es fehlt)
# ---------------------------------------------------------------------------
def _webview_holen(kern):
    try:
        import webview
        return webview
    except ImportError:
        pass
    import importlib
    import subprocess
    import tkinter as tk
    hinweis = tk.Tk()
    hinweis.title("PitVoice AI")
    hinweis.geometry("460x130")
    hinweis.configure(bg="#08080A")
    tk.Label(hinweis, text=L("Das neue Glas-Design wird eingerichtet.\nDas passiert nur beim ersten Start "
                           "und dauert etwa eine Minute.", "Setting up the new glass design.\\nThis only happens on the first start "
                           "and takes about a minute."),
             bg="#08080A", fg="#F2F3F5", font=("Segoe UI", 11)).pack(expand=True)
    hinweis.update()
    ergebnis = subprocess.run([kern._python_programm(), "-m", "pip", "install", "pywebview"],
                              capture_output=True, text=True,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    hinweis.destroy()
    if ergebnis.returncode != 0:
        print(ergebnis.stdout, ergebnis.stderr)
        return None
    importlib.invalidate_caches()
    try:
        import webview
        return webview
    except ImportError:
        traceback.print_exc()
        return None


def main(kern=None):
    """Startet das Glas-Fenster. Gibt False zurück, wenn es nicht geht (dann kommt das alte Fenster)."""
    if kern is None:
        import acc_app as kern
    if not os.path.exists(OBERFLAECHE):
        print("Ordner 'oberflaeche' fehlt, nehme das alte Fenster.")
        return False
    webview = _webview_holen(kern)
    if webview is None:
        return False
    bruecke = Bruecke(kern)
    bruecke._webview = webview
    fenster = webview.create_window("PitVoice AI", OBERFLAECHE, js_api=bruecke,
                                    width=1360, height=860, min_size=(1100, 700),
                                    background_color="#050506")
    fenster.events.closing += bruecke.beenden

    def nach_start():
        # Handy-Anzeige und Overlay wieder einschalten, wenn sie beim letzten Mal an waren
        if bruecke._e.get("handy"):
            bruecke.handy(True)
        if bruecke._e.get("overlay"):
            bruecke.overlay(True)

    fenster.events.loaded += lambda: threading.Thread(target=nach_start, daemon=True).start()
    try:
        webview.start(gui="edgechromium", private_mode=False)
    except Exception:
        traceback.print_exc()
        try:
            webview.start(private_mode=False)
        except Exception:
            traceback.print_exc()
            return False
    return True


if __name__ == "__main__":
    if not main():
        import acc_app
        acc_app.main()
