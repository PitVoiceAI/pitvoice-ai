# acc_gedaechtnis.py
# Der Renningenieur merkt sich pro Strecke und Auto:
#   - deinen Verbrauch pro Runde und deine typische Rundenzeit (für den Startsprit)
#   - deine Bestzeiten über alle Sessions (für "Fortschritt pro Strecke")
# Gespeichert in strecken_daten.json im Programmordner.
#
# Diese Datei startet man nicht selbst.

import json
import os
import threading
import time

ORDNER = os.path.dirname(os.path.abspath(__file__))
DATEI = os.path.join(ORDNER, "strecken_daten.json")
_sperre = threading.Lock()


def _schluessel(strecke, auto):
    return f"{strecke}|{auto}"


def alles_laden():
    try:
        with open(DATEI, encoding="utf-8") as datei:
            return json.load(datei)
    except (OSError, ValueError):
        return {}


def _speichern(daten):
    zwischen = DATEI + ".neu"
    with open(zwischen, "w", encoding="utf-8") as datei:
        json.dump(daten, datei, indent=1, ensure_ascii=False)
    os.replace(zwischen, DATEI)


def holen(strecke, auto):
    """Was wir über diese Strecke mit diesem Auto wissen (dict), oder {}."""
    if not strecke:
        return {}
    with _sperre:
        return alles_laden().get(_schluessel(strecke, auto), {})


def runde_merken(strecke, auto, verbrauch=None, rundenzeit_s=None):
    """Nach jeder sauberen Runde: gleitender Durchschnitt für Verbrauch und Rundenzeit."""
    if not strecke or (not verbrauch and not rundenzeit_s):
        return
    with _sperre:
        daten = alles_laden()
        eintrag = daten.setdefault(_schluessel(strecke, auto), {"strecke": strecke, "auto": auto})
        if verbrauch and 0.3 < verbrauch < 15:
            alt = eintrag.get("verbrauch")
            eintrag["verbrauch"] = round(verbrauch if alt is None else alt * 0.8 + verbrauch * 0.2, 3)
        if rundenzeit_s and 20 < rundenzeit_s < 1200:
            alt = eintrag.get("rundenzeit")
            eintrag["rundenzeit"] = round(rundenzeit_s if alt is None else alt * 0.8 + rundenzeit_s * 0.2, 3)
        eintrag["zuletzt"] = time.time()
        try:
            _speichern(daten)
        except OSError:
            pass


def bestzeit_merken(strecke, auto, zeit_ms, session):
    """Bestzeit einer Session für den Fortschritt. Eine Zeile pro Tag und Session-Art."""
    if not strecke or not zeit_ms or zeit_ms <= 0:
        return
    tag = time.strftime("%Y-%m-%d")
    with _sperre:
        daten = alles_laden()
        eintrag = daten.setdefault(_schluessel(strecke, auto), {"strecke": strecke, "auto": auto})
        verlauf = eintrag.setdefault("bestzeiten", [])
        for zeile in verlauf:
            if zeile["tag"] == tag and zeile["session"] == session:
                zeile["zeit"] = min(zeile["zeit"], zeit_ms)
                break
        else:
            verlauf.append({"tag": tag, "session": session, "zeit": zeit_ms})
        del verlauf[:-200]
        try:
            _speichern(daten)
        except OSError:
            pass
