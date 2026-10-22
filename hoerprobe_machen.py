# hoerprobe_machen.py
# Macht die Hörproben für die Webseite: Fritz (Deutsch) und Sam (Englisch) mit Funk-Effekt,
# genau so, wie sie im Programm klingen (Piper-Stimmen, frei lizenziert).
# Die Dateien landen in webseite-dateien\hoerprobe_de.wav und hoerprobe_en.wav.
# Starten: Doppelklick auf "Hoerprobe-machen.cmd".

import os
import sys
import wave

import numpy as np

ORDNER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ORDNER)
os.chdir(ORDNER)

import acc_sprache  # noqa: E402
import acc_stimme   # noqa: E402

SPRUECHE = {
    "de": ("de_DE-thorsten-high", [
        "Box, Box! Komm diese Runde rein, wir tanken 26 Liter. Du kommst vor dem Auto auf P4 wieder raus.",
        "Hinten macht der Wagen hinter dir Druck, nur noch 0,9 Sekunden. Sauber bleiben.",
        "In Kurve 2 bremst du etwa 20 Meter zu früh. Da liegen gut sechs Zehntel.",
    ]),
    "en": ("en_GB-northern_english_male-medium", [
        "Box, box! Box this lap, we add 26 litres. You'll rejoin ahead of the car in P4.",
        "The car behind is pushing, only 0.9 seconds now. Keep it clean.",
        "Turn 2, you're braking about 20 metres too early. There's six tenths in that.",
    ]),
}
RATE = 24000


def machen(sprache):
    stimme_datei, saetze = SPRUECHE[sprache]
    if not acc_stimme.piper_installiert(stimme_datei):
        print(f"Stimme {stimme_datei} fehlt im Ordner 'stimmen'. Bitte einmal im Programm laden.")
        return
    acc_sprache.setzen(sprache)
    stimme = acc_stimme.PiperStimme(stimme_datei, 2)
    teile = [np.zeros(int(RATE * 0.3), dtype=np.float32)]
    for satz in saetze:
        audio, rate = stimme.erzeugen(acc_stimme.aussprechen(satz, False))
        audio = acc_stimme.funk_effekt(audio, rate, 2, toene=True)
        teile.append(acc_stimme.auf_rate(audio, rate, RATE))
        teile.append(np.zeros(int(RATE * 0.9), dtype=np.float32))
    gesamt = np.concatenate(teile)
    gesamt = gesamt / (np.max(np.abs(gesamt)) + 1e-9) * 0.89
    ziel = os.path.join(ORDNER, "webseite-dateien", f"hoerprobe_{sprache}.wav")
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    with wave.open(ziel, "wb") as datei:
        datei.setnchannels(1)
        datei.setsampwidth(2)
        datei.setframerate(RATE)
        datei.writeframes((gesamt * 32767).astype(np.int16).tobytes())
    print("Fertig:", ziel)


if __name__ == "__main__":
    for s in ("de", "en"):
        try:
            machen(s)
        except Exception as fehler:
            print(f"Fehler bei {s}: {type(fehler).__name__}: {fehler}")
