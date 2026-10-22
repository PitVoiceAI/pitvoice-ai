# acc_funktest.py
# Schritt 4a des ACC-Renningenieurs: Funktest für die Sprachsteuerung.
#
# Taste am Lenkrad gedrückt halten -> sprechen -> loslassen.
# Das Programm schreibt auf, was es verstanden hat, und sagt es dir zurück.
#
# Einmalig vorher installieren (in der Eingabeaufforderung):
#   py -3.13 -m pip install faster-whisper sounddevice pywin32 numpy
#
# Starten mit:  py -3.13 acc_funktest.py
# Beenden mit:  Strg + C
# Andere Funktaste wählen: im Programmfenster unter Einstellungen.

import os
import time

import numpy as np                       # schnelles Rechnen mit Zahlenreihen (Audio)
import sounddevice as sd                 # nimmt vom Mikrofon auf
import win32com.client                   # Windows-Sprachausgabe
from faster_whisper import WhisperModel  # Spracherkennung (offline)

import acc_funktaste                     # liest die Funktaste, ohne das Force Feedback zu stören

ORDNER = os.path.dirname(os.path.abspath(__file__))
ABTASTRATE = 16000          # Whisper möchte 16.000 Messwerte pro Sekunde
NACHLAUF_S = 0.3            # nach dem Loslassen noch kurz weiter aufnehmen

# Wörter, die im Rennen oft vorkommen. Hilft der Erkennung, sie richtig zu schreiben.
WORTHILFE = ("Renningenieur. Abstand zu P1, P2, P3, Vordermann, Hintermann. "
             "Wie viel Sprit habe ich noch? Tank, Boxenstopp, Boxenfenster, Runden. "
             "Musik aus, Musik weiter, nächstes Lied, lauter, leiser.")


# ---------------------------------------------------------------------------
# 1) Funktaste (Lenkrad, Steuerkreuz oder Tastatur)
# ---------------------------------------------------------------------------
class Funktaste:
    def __init__(self):
        self.taste = None

    def einrichten(self):
        try:
            self.taste = acc_funktaste.Funktaste()
            print(f"Funktaste: {acc_funktaste.beschreibung()}")
            return
        except LookupError as fehler:
            print(fehler)
        print("\n>>> Drück jetzt die Taste, mit der du funken willst (15 Sekunden) <<<")
        ergebnis = acc_funktaste.lernen(15)
        if not ergebnis:
            raise SystemExit("Keine Taste gedrückt.")
        print(f"Gespeichert: {ergebnis}")
        self.taste = acc_funktaste.Funktaste()
        while self.gedrueckt():          # warten, bis losgelassen
            time.sleep(0.01)

    def gedrueckt(self):
        return self.taste.gedrueckt()


# ---------------------------------------------------------------------------
# 2) Aufnahme vom Mikrofon, solange die Taste gedrückt ist
# ---------------------------------------------------------------------------
def aufnehmen(taste):
    teile = []
    with sd.InputStream(samplerate=ABTASTRATE, channels=1, dtype="float32") as strom:
        while taste.gedrueckt():
            daten, _ = strom.read(ABTASTRATE // 20)     # jeweils 0,05 Sekunden
            teile.append(daten[:, 0].copy())
        nachlauf, _ = strom.read(int(ABTASTRATE * NACHLAUF_S))
        teile.append(nachlauf[:, 0].copy())
    return np.concatenate(teile)


# ---------------------------------------------------------------------------
# 3) Sprachausgabe mit der eingebauten Windows-Stimme
# ---------------------------------------------------------------------------
class Sprecher:
    def __init__(self):
        self.stimme = win32com.client.Dispatch("SAPI.SpVoice")
        for kandidat in self.stimme.GetVoices():
            beschreibung = kandidat.GetDescription()
            if "German" in beschreibung or "Deutsch" in beschreibung:
                self.stimme.Voice = kandidat
                break
        print(f"Stimme: {self.stimme.Voice.GetDescription()}")
        self.stimme.Rate = 2            # etwas schneller als normal (-10 bis 10)

    def sagen(self, text):
        self.stimme.Speak(text)


# ---------------------------------------------------------------------------
# 4) Hauptprogramm
# ---------------------------------------------------------------------------
def main():
    taste = Funktaste()
    taste.einrichten()

    mikrofon = sd.query_devices(kind="input")["name"]
    print(f"Mikrofon: {mikrofon}")

    sprecher = Sprecher()

    print("\nLade Spracherkennung ...")
    print("(Beim ersten Start wird das Modell heruntergeladen, ca. 500 MB. Das dauert etwas.)")
    erkennung = WhisperModel("small", device="cpu", compute_type="int8")

    print("\nFertig! Taste gedrückt halten, sprechen, loslassen. (Beenden mit Strg + C)\n")
    sprecher.sagen("Funk ist bereit.")

    try:
        while True:
            if not taste.gedrueckt():
                time.sleep(0.02)
                continue

            audio = aufnehmen(taste)
            dauer = len(audio) / ABTASTRATE
            if dauer < 0.5:
                print("(zu kurz gedrückt)")
                continue

            start = time.perf_counter()
            abschnitte, _ = erkennung.transcribe(audio, language="de", beam_size=1,
                                                 initial_prompt=WORTHILFE)
            text = " ".join(a.text for a in abschnitte).strip()
            rechenzeit = time.perf_counter() - start

            if not text:
                print(f"Nichts verstanden ({dauer:.1f} s Aufnahme)")
                sprecher.sagen("Nicht verstanden.")
                continue

            print(f"Du: \"{text}\"   ({dauer:.1f} s gesprochen, {rechenzeit:.2f} s erkannt)")
            sprecher.sagen(f"Verstanden: {text}")

    except KeyboardInterrupt:
        print("\nBeendet.")


if __name__ == "__main__":
    main()
