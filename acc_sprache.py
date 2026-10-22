# acc_sprache.py
# Sprache des Programms: Deutsch (Standard) oder Englisch.
# Überall, wo etwas gesagt oder angezeigt wird, steht L("deutscher Text", "English text").
# L gibt je nach Einstellung den einen oder den anderen Text zurück.
#
# Diese Datei startet man nicht selbst.

import json
import os

SPRACHEN = {"de": "Deutsch", "en": "English"}


def _aus_einstellungen():
    """Die Sprache wird gleich beim Programmstart gelesen, damit alle Texte von Anfang an stimmen.
    Ein Wechsel gilt deshalb erst nach einem Neustart des Programms."""
    try:
        pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "einstellungen.json")
        with open(pfad, encoding="utf-8") as datei:
            return "en" if json.load(datei).get("sprache") == "en" else "de"
    except (OSError, ValueError, AttributeError):
        return "de"


SPRACHE = os.environ.get("ACC_SPRACHE") or _aus_einstellungen()      # "de" oder "en"


def setzen(sprache):
    global SPRACHE
    SPRACHE = "en" if sprache == "en" else "de"


def englisch():
    return SPRACHE == "en"


def L(de, en):
    """Deutscher oder englischer Text, je nach Einstellung."""
    return en if SPRACHE == "en" else de


def komma(zahl, stellen=1):
    """1.4 -> "1,4" auf Deutsch, "1.4" auf Englisch."""
    text = f"{zahl:.{stellen}f}"
    return text if SPRACHE == "en" else text.replace(".", ",")
