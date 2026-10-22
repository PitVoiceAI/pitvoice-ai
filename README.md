# PitVoice AI

**Kostenloser KI-Renningenieur für Assetto Corsa Competizione** · *Free AI race engineer for Assetto Corsa Competizione*

🌐 [pitvoice.com](https://pitvoice.com) · 📧 info@pitvoice.com

---

## Deutsch

PitVoice AI liest die Live-Daten aus ACC und funkt dir, was du bei 250 km/h nicht selbst ausrechnen kannst: Abstände nach vorne und hinten, Sprit und Boxenfenster, wo du nach dem Stopp rauskommst, Regen, Flaggen, Track Limits. Halte eine Taste am Lenkrad und frag einfach in normalen Sätzen. Nach dem Rennen gibt es eine kurze Auswertung, und die Telemetrie zeigt Kurve für Kurve, wo deine Zehntel liegen.

- Sprachausgabe mit Funk-Effekt (Deutsch und Englisch)
- KI online über Groq (kostenlos, eigener Schlüssel) oder komplett lokal
- Cockpit, Live-Karte, Telemetrie, Overlay und eine Ansicht fürs Handy oder Tablet
- Alles läuft auf deinem PC, keine Anmeldung

**Installieren:** Das fertige Setup gibt es auf [pitvoice.com](https://pitvoice.com). Es lädt Python und alle Bausteine selbst.

**Aus dem Quellcode starten:** Python 3.13 installieren, dann `python acc_app.py` im Programmordner. Fehlende Pakete installiert das Programm beim ersten Start.

## English

PitVoice AI reads ACC's live data and radios what you can't work out at 250 km/h: gaps ahead and behind, fuel and pit window, where you rejoin after a stop, rain, flags and track limits. Hold a wheel button and ask in plain sentences. After the race you get a short debrief, and the telemetry shows corner by corner where your tenths are.

**Install:** get the setup from [pitvoice.com](https://pitvoice.com). **Run from source:** Python 3.13, then `python acc_app.py`.

---

## Ordner / Folders

| Ordner | Inhalt |
|---|---|
| `acc_*.py` | Das Programm (Python) |
| `oberflaeche/` | Die Oberfläche der App, Overlay und Handy-Ansicht (HTML/JS/CSS) |
| `setup/` | Das Setup mit [Inno Setup 6](https://jrsoftware.org/isinfo.php): `PitVoice-AI.iss` und Bilder. Zum Bauen den Programmordner als `setup/programm/` daneben legen und `Setup-bauen.cmd` starten. `einrichten.py` erledigt nach dem Kopieren die Einrichtung (Pakete, ACC, Stimme). |
| `werkzeuge/` | Hilfsskripte, z. B. für die Hörproben der Webseite |

## Lizenz / License

GPL-3.0, siehe [LICENSE](LICENSE). Hinweise zu verwendeten Bibliotheken und Stimmen: [DRITTANBIETER.txt](DRITTANBIETER.txt).

PitVoice AI ist ein unabhängiges Fan-Projekt und kein offizielles Produkt von Kunos Simulazioni oder 505 Games. „Assetto Corsa Competizione“ ist eine Marke der jeweiligen Inhaber.

*PitVoice AI is an independent fan project, not affiliated with Kunos Simulazioni or 505 Games.*
