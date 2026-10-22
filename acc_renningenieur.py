# acc_renningenieur.py
# Schritt 4b: Der Renningenieur. Verbindet alles:
#   - Live-Daten aus ACC (acc_speicher.py)
#   - Abstände zum ganzen Feld (acc_abstaende.py)
#   - Spritrechnung (acc_sprit.py)
#   - Funk: Lenkradtaste, Spracherkennung (acc_funktest.py), Stimme (acc_stimme.py)
#   - Musiksteuerung über die Windows-Medientasten
#
# Alle Dateien müssen im selben Ordner liegen.
# Starten mit:  py -3.13 acc_renningenieur.py
# Beenden mit:  Strg + C

import math
import os
import random
import re
import threading
import time
import warnings

# Warnungen beim Laden der Spracherkennung ausblenden
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
warnings.filterwarnings("ignore")

import acc_sprit
from acc_abstaende import AccVerbindung
from acc_sprit import VerbrauchsMesser, restrunden_berechnen, strategie_berechnen
from acc_protokoll import Protokoll, boxenverlust, wiedereinstieg
import acc_gedaechtnis
import acc_telemetrie
from acc_sprache import L, englisch, komma


# ---------------------------------------------------------------------------
# 1) Rennstand: sammelt im Hintergrund ständig alle Daten
# Ein "Thread" ist wie ein zweites Programm, das gleichzeitig läuft
# (ähnlich wie task.spawn in Roblox). So kommen die Daten weiter rein,
# während du sprichst oder die Erkennung rechnet.
# ---------------------------------------------------------------------------
class Rennstand:
    def __init__(self):
        self.acc = AccVerbindung()
        self.messer = VerbrauchsMesser()
        self.protokoll = Protokoll()
        self.telemetrie = acc_telemetrie.Aufzeichnung()
        self.speicher = None
        self.physik = None
        self.grafik = None
        self.statisch = None
        # Die Sperre verhindert, dass beide Threads gleichzeitig an den Daten arbeiten
        self.sperre = threading.Lock()
        self.aktiv = False
        self.thread = None

    def starten(self):
        from acc_speicher import AccSpeicher
        self.speicher = AccSpeicher()
        self.aktiv = True
        self.thread = threading.Thread(target=self._schleife, daemon=True)
        self.thread.start()

    def stoppen(self):
        self.aktiv = False
        if self.thread:
            self.thread.join(timeout=2)
        self.acc.abmelden()
        self.acc.sock.close()

    def _schleife(self):
        while self.aktiv:
            with self.sperre:
                self.acc.pflegen()
                self.acc.empfangen()
                physik, grafik, statisch = self.speicher.lesen()
                self.physik, self.grafik, self.statisch = physik, grafik, statisch
                if grafik.status != 0:
                    try:
                        self.telemetrie.aufzeichnen(physik, grafik)
                    except Exception:
                        pass
                    self.messer.aktualisieren(physik.tank, grafik.runden_fertig,
                                              grafik.in_boxengasse or grafik.in_box,
                                              grafik.i_letzte_zeit)
            time.sleep(0.02)   # dem anderen Thread kurz die Sperre überlassen

    def acc_laeuft(self):
        return self.grafik is not None and self.grafik.status != 0



# ---------------------------------------------------------------------------
# 2) Verstehen: Was will der Fahrer?
# Wir suchen nach Schlüsselwörtern. Die Reihenfolge ist wichtig:
# erst die speziellen Themen, ganz am Ende die allgemeinen.
# ---------------------------------------------------------------------------
ZAHLWOERTER = {
    "eins": 1, "ein": 1, "eine": 1, "einen": 1, "zwei": 2, "drei": 3, "vier": 4,
    "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11,
    "zwölf": 12, "dreizehn": 13, "vierzehn": 14, "fünfzehn": 15, "sechzehn": 16,
    "siebzehn": 17, "achtzehn": 18, "neunzehn": 19, "zwanzig": 20,
    "einundzwanzig": 21, "zweiundzwanzig": 22, "dreiundzwanzig": 23,
    "vierundzwanzig": 24, "fünfundzwanzig": 25, "sechsundzwanzig": 26,
    "siebenundzwanzig": 27, "achtundzwanzig": 28, "neunundzwanzig": 29, "dreißig": 30,
}

# Diese Wörter helfen der Spracherkennung, Rennbegriffe richtig zu schreiben
WORTHILFE = L("Renningenieur. Abstand zu P1, P2, P3, Vordermann, Hintermann, Führender. "
             "Sprit, Tank, Verbrauch, Boxenstopp, Boxenfenster, nachtanken, Pflichtstopp. "
             "Reifendruck, Reifentemperatur, Bremsbeläge, Bremstemperatur, Schaden. "
             "Wetter, Regen, Streckentemperatur, Grip. Strafe, Flagge, Track Limits, Delta. "
             "TC, ABS, Motor-Map, Stint, Lagebericht. Wer ist auf der Strecke vor mir? "
             "Überrunden, blaue Flagge. Musik aus, nächstes Lied, lauter, leiser.",
              "Race engineer. Gap to P1, P2, P3, car ahead, car behind, leader. "
              "Fuel, tank, consumption, pit stop, pit window, refuel, mandatory stop. "
              "Tyre pressure, tyre temperature, brake pads, brake temperature, damage. "
              "Weather, rain, track temperature, grip. Penalty, flag, track limits, delta. "
              "TC, ABS, engine map, stint, situation report. Who is ahead of me on track? "
              "Lapping, blue flag. Music off, next song, louder, quieter, copy.")


def platz_finden(text):
    """Findet 'P3', 'Platz 3', 'Position drei' usw. und gibt die Zahl zurück."""
    treffer = re.search(r"\b(?:p|platz|position|pos)\s*(\d{1,2})\b", text)
    if treffer:
        return int(treffer.group(1))
    woerter = "|".join(sorted(ZAHLWOERTER, key=len, reverse=True))
    treffer = re.search(r"\b(?:p|platz|position)\s+(" + woerter + r")\b", text)
    if treffer:
        return ZAHLWOERTER[treffer.group(1)]
    return None


def enthaelt(text, *woerter):
    return any(wort in text for wort in woerter)


def ziel_finden(t):
    """Um welches Auto geht es? 'vorne', 'hinten', 'letzter', eine Platznummer oder None."""
    if (enthaelt(t, "letzter platz", "letzten platz", "letzte platz", "letzte auto", "letzten auto",
                 "schlusslicht", " letzter ", "ganz hinten")
            or re.search(r" (zum|dem|den) letzten (?!runde)", t)):
        return "letzter"
    if enthaelt(t, "vordermann", "vorderman", "vor mir", " vorne ", "vorderen", "vorausfahrend"):
        return "vorne"
    if enthaelt(t, "hintermann", "hinterman", "hinter mir", " hinten ", "hinteren", "verfolger"):
        return "hinten"
    if enthaelt(t, "führ", "spitze", "leader", " erste ", " ersten ", " erster "):
        return 1
    return platz_finden(t)


def normalisieren(text):
    """Kleinbuchstaben, ohne Satzzeichen, mit Leerzeichen am Rand (für die Stichwortsuche)."""
    t = text.lower().replace("-", " ")
    t = re.sub(r"[^\wäöüß ]", " ", t)     # Satzzeichen entfernen
    return " " + re.sub(r"\s+", " ", t).strip() + " "


STRECKEN_WOERTER = ("auf der strecke", "auf strecke", "auf der bahn", "physisch", "im verkehr",
                    "verkehr", "überrunde", "überrundet", "rundenrückstand", "blaue flagge für",
                    "wer kommt von hinten", "wer fährt direkt")


RAT_MUSTER = re.compile(r"\b(soll ich|sollte ich|sollen wir|was meinst du|was denkst du|empfiehlst|"
                        r"lohnt sich|lohnt es|macht es sinn|was würdest du|was rätst du|"
                        r"angreifen|attackieren|reifen schonen)\b")


# Englische Fragen: werden vor der Stichwortsuche in die deutschen Stichwörter übersetzt,
# damit die gleiche Erkennung für beide Sprachen funktioniert (die KI versteht ohnehin beides).
_EN_ZAHLEN = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
              "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
              "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "twenty five": 25,
              "thirty": 30, "forty": 40, "forty five": 45, "fifty": 50, "sixty": 60, "ninety": 90}
_EN_DE = [
    # Funk und Musik
    ("say that again", "wiederhol"), ("repeat", "wiederhol"), ("come again", "wiederhol"), ("pardon", "wie bitte"),
    ("radio silence off", "funkstille aus"), ("talk again", "wieder reden"), ("announcements on", "ansagen an"),
    ("radio silence", "funkstille"), ("be quiet", "sei still"), ("shut up", "halt den mund"),
    ("announcements off", "ansagen aus"), ("what can you do", "was kannst du"), ("what can i ask", "was kann ich fragen"),
    ("help", "hilfe"), ("next song", "musik nächst"), ("skip", "musik überspring"), ("previous song", "musik zurück"),
    ("music", "musik"), ("louder", " lauter"), ("volume up", " lauter"), ("quieter", " leiser"), ("volume down", " leiser"),
    # Rat
    ("should i", "soll ich"), ("should we", "sollen wir"), ("what do you think", "was meinst du"),
    ("do you recommend", "empfiehlst"), ("is it worth", "lohnt es"), ("what would you do", "was würdest du"),
    ("attack", "angreifen"), ("save the tyres", "reifen schonen"), ("save my tyres", "reifen schonen"),
    # Reifen
    ("wet tyres", "regenreifen"), ("wet tires", "regenreifen"), ("wets", "regenreifen"), ("dry tyres", "slicks"),
    ("tyre pressures", "reifendruck"), ("tire pressures", "reifendruck"), ("tyre pressure", "reifendruck"),
    ("tire pressure", "reifendruck"), ("pressures", "reifendruck"), ("pressure", "druck"),
    ("adjust", "anpass"), ("change", "ändern"), ("next stint", "nächsten stint"),
    ("tyre temps", "reifen temp"), ("tire temps", "reifen temp"), ("tyre temperature", "reifen temp"),
    ("tire temperature", "reifen temp"), ("compound", "mischung"), ("which tyres", "welche reifen"),
    ("tyres", "reifen"), ("tires", "reifen"), ("tyre", "reifen"), ("tire", "reifen"), ("degrad", "abbau"),
    # Bremsen
    ("brake bias", "bremsbalance"), ("brake pads", "brems beläge"), ("pads", "beläge"), ("brakes", "brems"),
    ("brake", "brems"), ("wear", "verschleiß"),
    # Box und Sprit
    ("i am in the pits", "ich bin in der box"), ("i'm in the pits", "ich bin in der box"), ("im in the pits", "ich bin in der box"),
    ("i'm pitting", "ich komme in die box"), ("im pitting", "ich komme in die box"), ("boxing", "ich komme in die box"),
    ("pitting this lap", "ich komme in die box"), ("coming in", "ich komme in die box"),
    ("where will i rejoin", "wo komme ich raus"), ("where do i come out", "wo komme ich raus"),
    ("after the stop", "nach dem stopp"), ("who has pitted", "wer war an der box"), ("who pitted", "wer war an der box"),
    ("already pitted", "schon an der box"), ("without stopping", "ohne stopp"), ("without a stop", "ohne stopp"),
    ("no stop", "ohne stopp"), ("make it to the end", "schaffe ich es ohne"), ("save fuel", "sparen"),
    ("fuel for", "sprit für"), ("for the race", "fürs rennen"), ("at the start", "zum start"),
    ("consumption", "verbrauch"), ("per lap", "pro runde"), ("mandatory", "pflicht"),
    ("pit window", "box fenster"), ("pit stop", "boxenstopp"), ("pit lane", "boxengasse"), ("refuel", "nachtank"),
    ("pits", " box"), ("pit", " box"), ("box", " box"), ("fuel", "sprit"), ("litres", "liter"), ("liters", "liter"),
    # Rennleitung
    ("penalty", "strafe"), ("drive through", "durchfahrt"), ("flag", "flagge"), ("valid", "gültig"),
    ("track limits", "track limit"),
    # Wetter, Strecke, Auto
    ("weather", "wetter"), ("forecast", "vorhersage"), ("rain", "regen"), ("dry", "trocken"),
    ("track temp", "temperatur"), ("air temp", "temperatur"), ("temperature", "temperatur"),
    ("water", "wasser"), ("engine temp", "motortemp"), ("damage", "schaden"), ("traction", "traktion"),
    ("engine map", "motor map"), ("time of day", "uhrzeit"), ("what time is it", "wie spät"),
    # Gegner und Zeiten
    ("on track", "auf der strecke"), ("lapping", "überrunde"), ("lap down", "rundenrückstand"),
    ("car ahead", "vordermann"), ("car in front", "vordermann"), ("guy ahead", "vordermann"),
    ("ahead of me", "vor mir"), ("in front of me", "vor mir"), ("car behind", "hintermann"),
    ("behind me", "hinter mir"), ("the leader", "führend"), ("leader", "führend"), ("last place", "letzter platz"),
    ("fastest", "schnellste"), ("pole", "pole"), ("sector", "sektor"), ("where am i losing", "wo verlier"),
    ("where do i lose", "wo verlier"), ("losing time", "wo verlier"), ("consisten", "konstant"),
    ("catching", "aufhol"), ("catch", "einhol"), ("faster than", "schneller als"), ("slower than", "langsamer als"),
    ("compare", "vergleich"), ("overtake", "überhol"), ("pass him", "vorbei"),
    ("gap", "abstand"), ("how far", "wie weit"), ("distance", "abstand"),
    ("which lap", "welche runde"), ("what lap", "welche runde"), ("position", "position"), ("place", "platz"),
    ("lap time", "rundenzeit"), ("last lap", "letzte runde"), ("best lap", "beste runde"),
    ("how long", "wie lange"), ("time left", "restzeit"), ("how many laps", "wie viele runden"),
    ("laps left", "wie viele runden"), ("remaining", "verbleib"), ("minutes", "minuten"), ("minute", "minute"),
    ("hours", "stunden"), ("hour", "stunde"), ("laps", "runden"), ("lap", "runde"),
    ("situation report", "lagebericht"), ("sitrep", "lagebericht"), ("status", "status"), ("update", "update"),
    ("how is it going", "wie läufts"), ("how are we looking", "wie sieht"), ("overview", "überblick"),
    ("thanks", "danke"), ("thank you", "danke"), ("copy", "copy"), ("roger", "roger"), ("understood", "verstanden"),
]
_EN_MUSTER = [(re.compile(r"(?<![a-zäöüß])" + re.escape(en) + r"(?![a-zäöüß])"), " " + de + " ")
              for en, de in sorted(_EN_DE, key=lambda p: len(p[0]), reverse=True)]


def englisch_zu_deutsch(t):
    """Macht aus einer englischen Frage die deutschen Stichwörter ('gap to the car ahead' -> 'abstand vordermann')."""
    t = t.lower().replace("’", "'")
    for wort, zahl_wert in sorted(_EN_ZAHLEN.items(), key=lambda p: len(p[0]), reverse=True):
        t = re.sub(r"\b" + wort + r"\b", str(zahl_wert), t)
    t = re.sub(r"\bp\s*(\d{1,2})\b", r"platz \1", t)
    for muster, ersatz in _EN_MUSTER:
        t = muster.sub(ersatz, t)
    return t


def verstehen(text):
    """Gibt (absicht, zusatz) zurück, z. B. ("abstand", 3) oder ("sprit", None)."""
    if englisch():
        text = englisch_zu_deutsch(text)
    t = normalisieren(text)
    ziel = ziel_finden(t)
    if enthaelt(t, "regenreifen", "slicks", " wets", "reifenwahl", "trockenreifen", "regen reifen") and \
            enthaelt(t, "soll", "wann", "wechsel", "umsteigen", "zeit für", "lohnt", "brauche", "drauf"):
        return "reifenwahl", None
    # Reifendruck für den nächsten Stint (vor "rat", weil oft mit "soll ich" gefragt)
    if enthaelt(t, "druck") and enthaelt(t, "anpass", "einstell", "ändern", "nächsten stint", "beim stopp",
                                         "soll ich", "empfiehl", "optimal", "ideal", "richtig", "zu hoch", "zu niedrig"):
        return "druck_anpassen", None
    if RAT_MUSTER.search(t):
        return "rat", None
    # Wer fährt auf der Strecke vor/hinter mir (egal in welcher Runde)?
    if enthaelt(t, *STRECKEN_WOERTER) and not enthaelt(t, "streckentemp", "strecke temp", "grip"):
        return "strecke", "hinten" if ziel == "hinten" or enthaelt(t, "von hinten", "hinter") else "vorne"

    # --- Funk steuern ---
    if enthaelt(t, "wiederhol", "nochmal", "noch mal", "noch einmal", "was hast du gesagt",
                "wie bitte", "nicht verstanden", "sag das"):
        return "wiederholen", None
    if enthaelt(t, "ansagen an", "ansagen wieder", "sprich wieder", "rede wieder",
                "funkstille aus", "funkstille beenden", "melde dich wieder", "wieder reden"):
        return "ansagen_an", None
    if enthaelt(t, "funkstille", " ruhe ", "sei still", "sei leise", "klappe", "keine ansagen",
                "ansagen aus", "nicht stören", "halt den mund", "nicht mehr reden"):
        return "ansagen_aus", None
    if enthaelt(t, "was kannst du", "hilfe", "welche befehle", "was kann ich fragen",
                "was kann ich sagen"):
        return "hilfe", None

    # --- Musik und Lautstärke ---
    if enthaelt(t, "musik", " lied", "song", " track ", " titel", "spotify"):
        if enthaelt(t, "lauter"):
            return "musik_lauter", None
        if enthaelt(t, "leiser"):
            return "musik_leiser", None
        if enthaelt(t, "nächst", "überspring", "skip", "anderes lied", "anderer song", "weiter "):
            if enthaelt(t, "musik weiter", "weiter abspielen", "weiter spielen"):
                return "musik_pause", None
            return "musik_weiter", None
        if enthaelt(t, "zurück", "vorherig", "letzte lied", "letztes lied", "davor"):
            return "musik_zurueck", None
        return "musik_pause", None
    if enthaelt(t, " lauter", "lautstärke hoch", "lautstärke rauf"):
        return "musik_lauter", None
    if enthaelt(t, " leiser", "lautstärke runter"):
        return "musik_leiser", None

    # --- Rennleitung ---
    if enthaelt(t, "strafe", "penalty", "durchfahrt", "drive through", "stop and go",
                "stop go", "stopp and go"):
        return "strafe", None
    if enthaelt(t, "flagge"):
        return "flagge", None
    if enthaelt(t, "gültig", "track limit", "tracklimit", "abgekürzt", "streckenbegrenzung"):
        return "gueltig", None
    if enthaelt(t, "pflicht"):
        return "pflichtstopp", None

    # --- Startsprit: "Wie viel Sprit für 30 Minuten?", "Wie viel tanken fürs Rennen?" ---
    dauer = dauer_finden(t)
    if enthaelt(t, "sprit", "tank", "liter", "benzin", "fuel", "kraftstoff") and (
            dauer or enthaelt(t, "fürs rennen", "für das rennen", "für ein rennen", "zum start", "startsprit",
                              "beim start", "vor dem rennen", "für den start")):
        return "startsprit", dauer
    if enthaelt(t, "startsprit"):
        return "startsprit", dauer


    # --- Aussagen: der Fahrer meldet etwas ("Ich bin in der Box") ---
    if re.search(r"\b(ich bin|bin jetzt|bin gerade|ich stehe|stehe|ich fahre|fahre jetzt|ich komme|komme jetzt|"
                 r"bin|biege)\b.*\b(box|boxengasse|boxen|pit)", t) and not enthaelt(t, "muss", "soll", "wann", "wie viel"):
        return "box_jetzt", None

    # --- Boxenstopp: wo komme ich raus, was machen die Gegner ---
    if enthaelt(t, "wo komme ich raus", "wo komm ich raus", "rauskomme", "raus komme", "wieder raus",
                "wo lande ich", "nach dem stopp", "nach dem stop", "nach dem boxenstopp", "rejoin"):
        return "rauskommen", None
    if enthaelt(t, "undercut", "overcut", "gegner gestoppt", "schon gestoppt", "schon an der box",
                "schon in der box", "wer war an der box", "wer war in der box", "wer hat gestoppt",
                "die anderen gestoppt", "haben die anderen", "gegner an der box", "boxenstopps der"):
        return "gegner_box", None

    # --- Sprit und Box ---
    if enthaelt(t, "sparen", " spar ", "ohne stopp", "ohne stop", "ohne boxenstopp",
                "ohne zu tanken", "ohne tanken", "durchfahren", "reicht es ohne",
                "schaffe ich es ohne", "lift and coast"):
        return "spritsparen", None
    if enthaelt(t, "verbrauch") or (enthaelt(t, "pro runde") and enthaelt(t, "sprit", "liter", "tank")):
        return "verbrauch", None
    if enthaelt(t, " box", "boxen", "stopp", " stop ", " pit", "nachtank", "tanken",
                "reinkommen", "rein kommen", "reinfahren"):
        return "box", None
    if enthaelt(t, "sprit", "tank", "benzin", "fuel", "liter", "kraftstoff"):
        return "sprit", None

    # --- Bremsen und Reifen ---
    if enthaelt(t, "bremsbalance", "brake bias", "bremskraftverteilung"):
        return "bremsbalance", None
    if enthaelt(t, "brems", "belag", "beläge", "scheibe"):
        if enthaelt(t, "belag", "beläge", "verschleiß", "abgenutzt", "millimeter", "abnutzung"):
            return "bremsbelag", None
        return "bremstemp", None
    ohne_greifen = re.sub(r"\w*greif\w*", " ", t)      # "angreifen" ist keine Reifen-Frage
    if enthaelt(ohne_greifen, "reifen", "druck", " psi", "pneu", "slicks", "gummi"):
        if enthaelt(t, "abbau", "verschleiß", "lassen nach", "lässt nach") or re.search(r"\bbau(en|t)\b.*\bab\b", t):
            return "konstanz", None
        if enthaelt(t, "druck", " psi"):
            return "reifendruck", None
        if enthaelt(t, "temp", "warm", "kalt", "heiß", "grad"):
            return "reifentemp", None
        if enthaelt(t, "mischung", "welche reifen", "satz", "slicks", "regenreifen", "art"):
            return "reifenart", None
        return "reifen", None

    # --- Wetter und Strecke ---
    if enthaelt(t, "regen", "wetter", "regnet", " nass", "trocken", "wolken", "gewitter",
                "vorhersage", "schauer"):
        return "wetter", None
    if enthaelt(t, "grip", "haftung", "rutschig"):
        return "grip", None
    if enthaelt(t, "wasser", "motortemp", "motor temp", "überhitz", "kühlwasser"):
        return "wassertemp", None
    if enthaelt(t, "temperatur", "asphalt", "wie warm", "wie kalt", " grad", "hitze"):
        return "temperaturen", None
    if enthaelt(t, "wind"):
        return "wind", None

    # --- Auto ---
    if enthaelt(t, "schaden", "kaputt", "beschädigt", "damage", "reparatur", "repariert"):
        return "schaden", None
    if enthaelt(t, " tc ", "traktion", " abs ", "motor map", "motormap", "motor-map",
                " map ", "mapping", "elektronik", "einstellung"):
        return "elektronik", None
    if enthaelt(t, "stint", "fahrzeit", "fahrerwechsel"):
        return "stint", None
    if enthaelt(t, "uhrzeit", "wie spät", "tageszeit", "uhr ist es"):
        return "uhrzeit", None

    # --- Zeiten und Gegner ---
    if enthaelt(t, "delta", "wie bin ich unterwegs", "schneller als meine", "aktuelle runde",
                "diese runde", "geschätzt"):
        return "delta", None
    if enthaelt(t, "schnellste", "schnellster", "fastest", "bestzeit im feld",
                "beste runde im feld", "beste zeit im feld"):
        return "schnellste", None
    if enthaelt(t, "pole", "zur bestzeit", "auf die bestzeit", "zur schnellsten", "auf die schnellste",
                "fehlt mir auf", "fehlt mir zur"):
        return "pole", None
    if enthaelt(t, "sektor") or (enthaelt(t, "wo ") and enthaelt(t, "verlier", "langsam", "zeit liegen",
                                                                    "zeit lasse", "fehlt mir", "besser werden")):
        return "sektoren", ziel
    if enthaelt(t, "konstant", "konstanz", "abbau", "werde ich langsamer",
                "werden meine zeiten", "werden meine runden", "meine pace", "mein tempo", "gleichmäßig"):
        return "konstanz", None
    if enthaelt(t, "aufhol", "einhol", "schneller als", "langsamer als", "vergleich", " pace",
                "vorbei", "überhol", "kriege ich", "krieg ich", "schnapp",
                "verliere ich", "verlier ich", "hole ich", "dran ") or \
            (ziel is not None and enthaelt(t, "rundenzeit", "zeiten", " zeit ", "fährt er", "fährt der")):
        return "vergleich", ziel or "vorne"
    if ziel is not None:
        return "abstand", ziel
    if enthaelt(t, "abstand", "lücke", "gap", "wie weit"):
        return "abstand", "vorne"

    # --- Rennen allgemein ---
    if enthaelt(t, "welche runde", "runde bin ich", "wievielte runde", "wie vielte runde",
                "wievielten runde", "wie vielten runde"):
        return "runde", None
    if enthaelt(t, "position", "platz", "wo bin ich", "wievielte", "wie vielte", "wievielter",
                "wie vielter", "wie viele autos", "wie viele fahrer", "teilnehmer"):
        return "position", None
    if enthaelt(t, "rundenzeit", "letzte runde", "beste runde", "bestzeit", "zeiten", "meine zeit"):
        return "rundenzeit", None
    if enthaelt(t, "wie lange", "restzeit", "wie viele runden", "wieviele runden", "noch runden",
                "verbleib", "zeit übrig", "minuten", "rennende", "bis zum ende", "bis ins ziel"):
        return "rest", None
    if enthaelt(t, "lagebericht", "status", "zusammenfassung", "update", "wie sieht",
                "überblick", " lage ", "wie stehts", "wie steht es", "wie läufts", "wie läuft es",
                "situation", "infos"):
        return "lagebericht", None
    if enthaelt(t, "danke", "copy", "roger", "alles klar", "verstanden", "super", "top "):
        return "danke", None
    return "unbekannt", None


TRENNER = re.compile(r"\s*(?:,|;|\?|\.|\bund\b|\baußerdem\b|\bsowie\b|\bplus\b|\bzusätzlich\b|\band\b|\balso\b)\s*",
                     re.IGNORECASE)
MIT_ZIEL = {"abstand", "vergleich", "strecke"}


def verstehen_mehrfach(text):
    """Zerlegt kombinierte Fragen ("Wer ist vor mir und wie viel Sprit habe ich?")
    und gibt eine Liste von (absicht, zusatz) zurück, ohne Doppelte."""
    ganz = verstehen(text)
    teile = [teil for teil in TRENNER.split(text) if teil and len(teil.strip()) > 2]
    if len(teile) <= 1:
        return [ganz]
    ergebnisse = []
    letztes_ziel = None
    for teil in teile:
        absicht, zusatz = verstehen(teil)
        if absicht == "unbekannt":
            continue
        if absicht in MIT_ZIEL:
            eigenes_ziel = ziel_finden(normalisieren(teil))
            if eigenes_ziel is None and letztes_ziel is not None:
                zusatz = letztes_ziel        # "... und wie viel Abstand habe ich?" -> gleiches Auto
            letztes_ziel = zusatz
        if (absicht, zusatz) not in ergebnisse:
            ergebnisse.append((absicht, zusatz))
    return ergebnisse or [ganz]


# ---------------------------------------------------------------------------
# 3) Antworten bauen
# Immer in ganzen, ausformulierten Sätzen, wie ein Renningenieur, der sauber funkt.
# Zahlen mit Komma, damit die deutsche Stimme "vier Komma zwei" sagt.
# ---------------------------------------------------------------------------
REGEN_NAMEN = L(["kein Regen", "Nieselregen", "leichter Regen", "mittlerer Regen",
                 "starker Regen", "Gewitter"],
                ["no rain", "drizzle", "light rain", "medium rain", "heavy rain", "a thunderstorm"])
# Wie der Regen in einem Satz klingt: "Aktuell ist es trocken." / "Aktuell gibt es leichten Regen."
REGEN_JETZT = L(["ist es trocken", "gibt es Nieselregen", "gibt es leichten Regen",
                 "gibt es mittleren Regen", "gibt es starken Regen", "gibt es ein Gewitter"],
                ["it is dry", "there is drizzle", "there is light rain", "there is medium rain",
                 "there is heavy rain", "there is a thunderstorm"])
REGEN_SPAETER = L(["bleibt es trocken", "wird Nieselregen erwartet", "wird leichter Regen erwartet",
                   "wird mittlerer Regen erwartet", "wird starker Regen erwartet", "wird ein Gewitter erwartet"],
                  ["it stays dry", "drizzle is expected", "light rain is expected", "medium rain is expected",
                   "heavy rain is expected", "a thunderstorm is expected"])
GRIP_SAETZE = L(["Die Strecke ist noch grün, es liegt kaum Gummi und der Grip ist niedrig.",
               "Die Strecke ist schnell, der Grip ist gut.",
               "Die Strecke ist optimal, der Grip ist so gut wie es geht.",
               "Die Strecke ist schmierig, sei vorsichtig mit dem Grip.",
               "Die Strecke ist feucht, der Grip ist deutlich schlechter.",
               "Die Strecke ist nass, der Grip ist niedrig.",
               "Die Strecke ist überflutet, pass auf Aquaplaning auf."],
                ["The track is still green, there is hardly any rubber down and grip is low.",
                 "The track is fast, grip is good.",
                 "The track is optimal, grip is as good as it gets.",
                 "The track is greasy, be careful with the grip.",
                 "The track is damp, grip is clearly worse.",
                 "The track is wet, grip is low.",
                 "The track is flooded, watch out for aquaplaning."])
FLAGGEN_NAMEN = L({0: "Gerade ist keine Flagge draußen.",
                 1: "Es ist die blaue Flagge draußen, ein schnelleres Auto ist hinter dir.",
                 2: "Es ist die gelbe Flagge draußen, bitte vorsichtig und nicht überholen.",
                 3: "Es ist die schwarze Flagge draußen, du wirst disqualifiziert.",
                 4: "Es ist die weiße Flagge draußen, ein langsames Auto ist auf der Strecke.",
                 5: "Die Zielflagge ist draußen.",
                 6: "Die Strafflagge ist draußen, du hast eine Strafe bekommen.",
                 7: "Es ist die grüne Flagge draußen, die Strecke ist frei.",
                 8: "Es ist die orange Flagge draußen, dein Auto ist beschädigt und muss an die Box."},
                  {0: "There is no flag out right now.",
                   1: "Blue flag, a faster car is behind you.",
                   2: "Yellow flag, be careful and no overtaking.",
                   3: "Black flag, you are disqualified.",
                   4: "White flag, there is a slow car on track.",
                   5: "The chequered flag is out.",
                   6: "Penalty flag, you have received a penalty.",
                   7: "Green flag, the track is clear.",
                   8: "Orange flag, your car is damaged and has to come to the pits."})
SCHADEN_ZONEN = L(["vorne", "hinten", "links", "rechts", "in der Mitte"],
                  ["front", "rear", "left", "right", "centre"])
RAEDER = L(["vorne links", "vorne rechts", "hinten links", "hinten rechts"],
           ["front left", "front right", "rear left", "rear right"])


def zahl(wert, stellen=1):
    """Deutsch mit Komma (1,4), Englisch mit Punkt (1.4)."""
    return komma(wert, stellen)


def zeit_sprechen(ms):
    """Rundenzeit ausgeschrieben: '2 Minuten 18,5 Sekunden' / '2 minutes 18.5 seconds'."""
    sekunden = ms / 1000
    minuten = int(sekunden // 60)
    rest = sekunden - minuten * 60
    if minuten:
        if englisch():
            return f"{minuten} {'minute' if minuten == 1 else 'minutes'} {zahl(rest)} seconds"
        return f"{minuten} {'Minute' if minuten == 1 else 'Minuten'} {zahl(rest)} Sekunden"
    return f"{zahl(rest)} {L('Sekunden', 'seconds')}"


def sekunden_sprechen(wert):
    """'1,4 Sekunden' bzw. '1 Sekunde'."""
    if zahl(wert) in ("1,0", "1.0"):
        return L("1 Sekunde", "1 second")
    return f"{zahl(wert)} {L('Sekunden', 'seconds')}"


def gueltige_zeit(ms):
    return ms is not None and 0 < ms < 10_000_000      # ACC meldet "keine Zeit" als riesige Zahl


# Automodelle in ACC (Nummer -> Marke), damit der Ingenieur "der Ferrari auf Platz 5" sagen kann
MARKEN = {}
for _marke, _nummern in {
        "Porsche": (0, 9, 23, 28, 34, 61, 85, 86), "Mercedes": (1, 25, 60, 84), "Ferrari": (2, 24, 26, 32),
        "Audi": (3, 19, 31, 52, 80), "Lamborghini": (4, 13, 16, 18, 29, 33), "McLaren": (5, 22, 35, 59),
        "Nissan": (6, 10), "BMW": (7, 27, 30, 53), "Bentley": (8, 11), "Aston Martin": (12, 20, 51),
        "Jaguar": (14,), "Lexus": (15,), "Honda": (17, 21), "Ford": (36,), "Alpine": (50,),
        "Chevrolet": (55,), "Ginetta": (56,), "KTM": (57, 82), "Maserati": (58, 83)}.items():
    for _nummer in _nummern:
        MARKEN[_nummer] = _marke

# Wie Gegner am Funk genannt werden: "auto" = "der Ferrari auf Platz 5", "name" = Nachname
KI_GESTOERT = False      # KI ist an, hat aber gerade nicht geantwortet (überlastet / Limit)
NAMEN_MODUS = "auto"


def jetzt_auf(auto, ende=""):
    """', der jetzt auf Platz 4 liegt' (für Vorhersagen nach dem Boxenstopp)"""
    platz = getattr(auto, "platz", None)
    if not platz:
        return ""
    return L(f", der jetzt auf Platz {platz} liegt{ende}", f", currently in P{platz}{ende}")


def anzeige_name(auto):
    """Name für das Fenster (immer der echte Nachname)."""
    if auto.fahrer and auto.fahrer != "?":
        return auto.fahrer.split()[-1]
    return f"#{auto.nummer}" if auto.nummer is not None else "?"


def name_von(auto, fall="nom", mit_platz=True):
    """Wie ein Gegner im Funk genannt wird.
    fall: "nom" (der Ferrari), "dat" (dem Ferrari), "akk" (den Ferrari).
    Fremdsprachige Namen spricht die Stimme oft falsch, deshalb standardmäßig Auto und Platz."""
    if NAMEN_MODUS == "name" and auto.fahrer and auto.fahrer != "?":
        return auto.fahrer.split()[-1]
    marke = MARKEN.get(getattr(auto, "modell", None))
    if englisch():                                   # Englisch kennt keine Fälle: "the Ferrari in P5"
        text = f"the {marke}" if marke else "the car"
        platz = getattr(auto, "platz", None) or (auto.position or None)
        return text + (f" in P{platz}" if mit_platz and platz else "")
    if marke:
        text = {"nom": "der", "dat": "dem", "akk": "den"}[fall] + " " + marke
    else:
        text = {"nom": "das Auto", "dat": "dem Auto", "akk": "das Auto"}[fall]
    platz = getattr(auto, "platz", None) or (auto.position or None)
    if mit_platz and platz:
        text += f" auf Platz {platz}"
    return text


def runden_wort(n):
    if englisch():
        return "one lap" if n == 1 else f"{n} laps"
    return "eine Runde" if n == 1 else f"{n} Runden"


def gross(text):
    return text[:1].upper() + text[1:]


def vier_raeder(werte, stellen=1, einheit=""):
    """'vorne links 27,4 PSI, vorne rechts 27,6 PSI, hinten links 26,9 PSI und hinten rechts 27,1 PSI'"""
    teile = [f"{rad} {zahl(wert, stellen)}{' ' + einheit if einheit else ''}"
             for rad, wert in zip(RAEDER, werte)]
    return ", ".join(teile[:3]) + L(" und ", " and ") + teile[3]


def strafe_text(code):
    if code in (1, 7, 19):
        art = L("eine Durchfahrtsstrafe", "a drive-through penalty")
    elif code in (2, 8):
        art = L("eine Stop-and-Go-Strafe von 10 Sekunden", "a 10 second stop-and-go penalty")
    elif code in (3, 9):
        art = L("eine Stop-and-Go-Strafe von 20 Sekunden", "a 20 second stop-and-go penalty")
    elif code in (4, 10):
        art = L("eine Stop-and-Go-Strafe von 30 Sekunden", "a 30 second stop-and-go penalty")
    elif code in (6, 12):
        art = L("eine Strafe, deine beste Rundenzeit wird gestrichen", "a penalty, your best lap time will be deleted")
    elif code == 14:
        art = L("eine Zeitstrafe, die nach dem Rennen aufgerechnet wird", "a time penalty that will be added after the race")
    else:
        art = L("eine Disqualifikation", "a disqualification")
    if 1 <= code <= 6:
        grund = L(", weil du die Strecke abgekürzt hast", " for cutting the track")
    elif 7 <= code <= 12:
        grund = L(", weil du in der Boxengasse zu schnell warst", " for speeding in the pit lane")
    elif code == 13:
        grund = L(", weil du den Pflichtstopp verpasst hast", " for missing the mandatory pit stop")
    elif code >= 19:
        grund = L(" wegen der Fahrerstint-Regeln", " for breaking the driver stint rules")
    else:
        grund = ""
    text = L(f"Du hast {art} bekommen{grund}.", f"You have received {art}{grund}.")
    if code in (1, 2, 3, 4, 7, 8, 9, 10, 19):
        text += L(" Du hast drei Runden Zeit, um sie abzusitzen.", " You have three laps to serve it.")
    return text


def sprit_lage(stand):
    """Rechnet die aktuelle Spritlage. Gibt (verbrauch, restrunden, ergebnis) oder None."""
    g, s = stand.grafik, stand.statisch
    verbrauch = stand.messer.verbrauch_schnitt() or (g.sprit_pro_runde if g.sprit_pro_runde > 0 else None)
    if not verbrauch:
        return None
    rundenzeit = stand.messer.rundenzeit_schnitt()
    if not rundenzeit and gueltige_zeit(g.i_letzte_zeit):
        rundenzeit = g.i_letzte_zeit / 1000
    restrunden = restrunden_berechnen(g.runden_fertig, g.runden_anteil, g.runden_gesamt,
                                      g.session_rest, rundenzeit, s.extrarunde)
    ergebnis = strategie_berechnen(stand.physik.tank, s.tank_max, verbrauch,
                                   restrunden or 0, g.runden_fertig, g.runden_anteil)
    return verbrauch, restrunden, ergebnis


def abstand_kurz(art, wert):
    """'1,2 Sekunden' / 'eine Runde' / None"""
    if art is None or wert is None:
        return None
    if art == "runden":
        return runden_wort(abs(wert))
    return sekunden_sprechen(abs(wert))


def auto_finden(stand, ziel):
    """Gibt (platz, auto, fehlertext) zurück."""
    acc = stand.acc
    if acc.verbindungs_id is None:
        return None, None, L("Ich habe gerade keine Verbindung zur Zeitnahme.", "I have no connection to timing right now.")
    mein_platz = acc.mein_platz()
    if mein_platz is None:
        return None, None, L("Ich sehe dein Auto in der Zeitnahme noch nicht.", "I can't see your car in the timing yet.")
    if ziel == "vorne":
        if mein_platz == 1:
            return None, None, L("Du führst das Rennen an, vor dir ist niemand.", "You are leading the race, there is nobody ahead of you.")
        platz = mein_platz - 1
    elif ziel == "hinten":
        platz = mein_platz + 1
    elif ziel == "letzter":
        platz = len(acc.rangliste())
    else:
        platz = ziel
    if platz == mein_platz:
        return None, None, L(f"Das bist du selbst, du liegst auf Platz {platz}.", f"That is you, you are in P{platz}.")
    auto = acc.auto_auf_platz(platz)
    if auto is None:
        if ziel == "hinten":
            return None, None, L("Hinter dir ist niemand, du bist Letzter.", "There is nobody behind you, you are last.")
        return None, None, L(f"Einen Platz {platz} gibt es in diesem Rennen nicht.", f"There is no P{platz} in this race.")
    return platz, auto, None


def antwort_abstand(stand, ziel):
    acc = stand.acc
    platz, auto, fehler = auto_finden(stand, ziel)
    if fehler:
        return fehler
    art, wert = acc.abstand_zu(auto)
    name = name_von(auto)
    if ziel == "vorne":
        wer = L(f"Vor dir liegt {name_von(auto, mit_platz=False)} auf Platz {platz}.", f"Ahead of you is {name_von(auto, mit_platz=False)} in P{platz}.")
    elif ziel == "hinten":
        wer = L(f"Hinter dir liegt {name_von(auto, mit_platz=False)} auf Platz {platz}.", f"Behind you is {name_von(auto, mit_platz=False)} in P{platz}.")
    else:
        wer = L(f"Auf Platz {platz} liegt {name_von(auto, mit_platz=False)}.", f"In P{platz} is {name_von(auto, mit_platz=False)}.")
    if art is None or wert is None:
        return wer + L(" Den Abstand berechne ich gerade noch.", " I'm still calculating the gap.")
    if not acc.ist_rennen():
        if wert >= 0:
            return wer + L(f" Seine Bestzeit ist {sekunden_sprechen(wert)} schneller als deine.", f" His best lap is {sekunden_sprechen(wert)} faster than yours.")
        return wer + L(f" Seine Bestzeit ist {sekunden_sprechen(-wert)} langsamer als deine.", f" His best lap is {sekunden_sprechen(-wert)} slower than yours.")
    if art == "runden":
        if wert > 0:
            return wer + L(f" Er liegt {runden_wort(abs(wert))} vor dir.", f" He is {runden_wort(abs(wert))} ahead of you.")
        return wer + L(f" Er liegt {runden_wort(abs(wert))} hinter dir.", f" He is {runden_wort(abs(wert))} behind you.")
    if wert >= 0:
        text = wer + L(f" Der Abstand zu ihm beträgt {sekunden_sprechen(wert)}.", f" The gap to him is {sekunden_sprechen(wert)}.")
    else:
        text = wer + L(f" Er ist {sekunden_sprechen(-wert)} hinter dir.", f" He is {sekunden_sprechen(-wert)} behind you.")
    return mit_zuspruch(text, stand) if ziel in ("vorne", "hinten") else text


def strecken_nachbar(stand, richtung):
    """Das Auto, das auf der Strecke direkt vor bzw. hinter dir fährt, egal in welcher Runde.
    Gibt (auto, sekunden, runden_unterschied) zurück, oder (None, None, None).
    runden_unterschied: 0 = gleiche Runde, -1 = eine Runde zurück (überrundet), +1 = eine Runde vor dir."""
    acc = stand.acc
    ich = acc.ich()
    if ich is None or ich.runden_zaehler is None:
        return None, None, None
    bester, bester_abstand = None, 2.0
    for auto in acc.autos.values():
        if auto is ich or auto.runden_zaehler is None or auto.ort in (2, 3, 4) or auto.kmh < 5:
            continue                              # in der Box oder steht
        if richtung == "vorne":
            anteil = (auto.spline - ich.spline) % 1.0
        else:
            anteil = (ich.spline - auto.spline) % 1.0
        if 0 < anteil < bester_abstand:
            bester, bester_abstand = auto, anteil
    if bester is None:
        return None, None, None

    unterschied = bester.gefahrene_strecke() - ich.gefahrene_strecke()
    if richtung == "vorne":
        runden = round(unterschied - bester_abstand)
        # Wann war das Auto da, wo ich jetzt bin?
        zeitpunkt = bester.zeitpunkt_bei(bester.gefahrene_strecke() - bester_abstand)
        sekunden = bester.zeiten[-1] - zeitpunkt if zeitpunkt is not None and bester.zeiten else None
        tempo = ich.kmh
    else:
        runden = round(unterschied + bester_abstand)
        # Wann war ich da, wo das Auto jetzt ist?
        zeitpunkt = ich.zeitpunkt_bei(ich.gefahrene_strecke() - bester_abstand)
        sekunden = ich.zeiten[-1] - zeitpunkt if zeitpunkt is not None and ich.zeiten else None
        tempo = bester.kmh
    if sekunden is None and acc.streckenlaenge_m and tempo > 20:
        sekunden = bester_abstand * acc.streckenlaenge_m / (tempo / 3.6)
    return bester, sekunden, runden


def antwort_strecke(stand, richtung):
    acc = stand.acc
    if acc.verbindungs_id is None:
        return L("Ich habe gerade keine Verbindung zur Zeitnahme.", "I have no connection to timing right now.")
    auto, sekunden, runden = strecken_nachbar(stand, richtung)
    if auto is None:
        return (L("Auf der Strecke ist gerade niemand direkt vor dir.", "There is nobody directly ahead of you on track right now.") if richtung == "vorne"
                else L("Auf der Strecke ist gerade niemand direkt hinter dir.", "There is nobody directly behind you on track right now."))
    liste = acc.rangliste()
    platz = L(f", der auf Platz {liste.index(auto) + 1} liegt", f", currently in P{liste.index(auto) + 1}") if auto in liste else ""
    wo = "vor" if richtung == "vorne" else "hinter"
    text = L(f"Auf der Strecke fährt direkt {wo} dir {name_von(auto, mit_platz=False)}{platz}.", f"Directly {'ahead of' if wo == 'vor' else 'behind'} you on track is {name_von(auto, mit_platz=False)}{platz}.")
    if sekunden is not None:
        text += L(f" Er ist {sekunden_sprechen(sekunden)} {wo} dir.", f" He is {sekunden_sprechen(sekunden)} {'ahead of' if wo == 'vor' else 'behind'} you.")
    if not acc.ist_rennen():
        return text
    if runden == 0:
        text += L(" Ihr fahrt in derselben Runde, er ist also ein direkter Gegner.", " You are on the same lap, so he is a direct rival.")
    elif runden < 0:
        text += L(f" Er liegt {runden_wort(-runden)} zurück.", f" He is {runden_wort(-runden)} down.")
        if richtung == "vorne":
            text += L(" Den kannst du überrunden.", " You can lap him.")
    else:
        text += L(f" Er hat {runden_wort(runden)} Vorsprung auf dich.", f" He is {runden_wort(runden)} ahead of you.")
        if richtung == "hinten":
            text += L(" Lass ihn vorbei, wenn er dran ist.", " Let him by when he gets to you.")
    return text


def antwort_vergleich(stand, ziel):
    acc = stand.acc
    platz, auto, fehler = auto_finden(stand, ziel)
    if fehler:
        return fehler
    ich = acc.ich()
    name = name_von(auto)
    seine, meine = auto.letzte_runde, ich.letzte_runde if ich else None
    if not gueltige_zeit(seine) or not gueltige_zeit(meine):
        return L(f"Von {name_von(auto, 'dat')} habe ich noch keine Rundenzeit, mit der ich vergleichen kann.", f"I don't have a lap time from {name_von(auto, 'dat')} yet to compare with.")
    unterschied = (seine - meine) / 1000      # positiv = du bist schneller
    text = (L(f"{gross(name)} ist seine letzte Runde in {zeit_sprechen(seine)} gefahren, "
            f"du in {zeit_sprechen(meine)}.", f"{gross(name)} did his last lap in {zeit_sprechen(seine)}, "
            f"you did {zeit_sprechen(meine)}."))
    if abs(unterschied) < 0.05:
        return text + L(" Ihr seid also gleich schnell.", " So you are equally fast.")
    if unterschied > 0:
        text += L(f" Du bist damit {sekunden_sprechen(unterschied)} pro Runde schneller als er.", f" So you are {sekunden_sprechen(unterschied)} per lap faster than him.")
    else:
        text += L(f" Er ist damit {sekunden_sprechen(-unterschied)} pro Runde schneller als du.", f" So he is {sekunden_sprechen(-unterschied)} per lap faster than you.")
    art, wert = acc.abstand_zu(auto)
    if acc.ist_rennen() and art == "sek" and wert is not None:
        lage = sprit_lage(stand)
        restrunden = lage[1] if lage and lage[1] is not None else None
        if wert > 0 and unterschied > 0:         # er ist vor dir, du holst auf
            runden = max(1, round(wert / unterschied))
            if restrunden is not None and runden > restrunden:
                text += (L(f" Bei einem Abstand von {sekunden_sprechen(wert)} reicht das aber nicht ganz, "
                         f"um ihn bis zum Rennende einzuholen.", f" With a gap of {sekunden_sprechen(wert)} that's not quite enough "
                         f"to catch him before the end of the race."))
            else:
                text += (L(f" Bei einem Abstand von {sekunden_sprechen(wert)} bist du in etwa "
                         f"{runden_wort(runden)} an ihm dran.", f" With a gap of {sekunden_sprechen(wert)} you should be on him in about "
                         f"{runden_wort(runden)}."))
        elif wert < 0 and unterschied < 0:       # er ist hinter dir und schneller
            runden = max(1, round(-wert / -unterschied))
            if restrunden is not None and runden > restrunden:
                text += L(" Bis zum Rennende sollte dein Vorsprung aber reichen.", " But your lead should be enough until the end of the race.")
            else:
                text += L(f" Er wird in etwa {runden_wort(runden)} an dir dran sein.", f" He should be on you in about {runden_wort(runden)}.")
    return text


def antwort_schnellste(stand):
    acc = stand.acc
    autos = [a for a in acc.autos.values() if gueltige_zeit(a.beste_runde)]
    if not autos:
        return L("Bisher hat noch niemand eine gezeitete Runde.", "Nobody has set a timed lap yet.")
    bester = min(autos, key=lambda a: a.beste_runde)
    if bester is acc.ich():
        return L(f"Du hast die schnellste Runde im Feld, mit {zeit_sprechen(bester.beste_runde)}.", f"You have the fastest lap in the field, with {zeit_sprechen(bester.beste_runde)}.")
    liste = acc.rangliste()
    platz = L(f" auf Platz {liste.index(bester) + 1}", f" in P{liste.index(bester) + 1}") if bester in liste else ""
    text = L(f"Die schnellste Runde hat {name_von(bester, mit_platz=False)}{platz} mit {zeit_sprechen(bester.beste_runde)} gefahren.", f"The fastest lap was set by {name_von(bester, mit_platz=False)}{platz} with {zeit_sprechen(bester.beste_runde)}.")
    ich = acc.ich()
    if ich and gueltige_zeit(ich.beste_runde):
        text += (L(f" Deine Bestzeit ist "
                 f"{sekunden_sprechen((ich.beste_runde - bester.beste_runde) / 1000)} langsamer.", f" Your best lap is "
                 f"{sekunden_sprechen((ich.beste_runde - bester.beste_runde) / 1000)} slower."))
    return text


def antwort_sprit(stand):
    lage = sprit_lage(stand)
    tank = stand.physik.tank
    if lage is None:
        return (L(f"Du hast noch {zahl(tank, 0)} Liter im Tank. Wie lange das reicht, kann ich dir "
                f"nach der ersten vollen Runde sagen.", f"You have {zahl(tank, 0)} litres in the tank. I can tell you how long that lasts "
                f"after the first full lap."))
    verbrauch, restrunden, e = lage
    text = L(f"Du hast noch {zahl(tank, 0)} Liter im Tank. Das reicht für {zahl(e['reicht_runden'])} Runden.", f"You have {zahl(tank, 0)} litres in the tank. That is enough for {zahl(e['reicht_runden'])} laps.")
    if restrunden is not None:
        if e["stopps"] == 0:
            text += L(" Damit kommst du bis ins Ziel.", " That gets you to the finish.")
        else:
            text += L(f" Bis ins Ziel fehlen dir noch {zahl(e['nachtanken'], 0)} Liter.", f" You are still {zahl(e['nachtanken'], 0)} litres short of the finish.")
    return text


def antwort_verbrauch(stand):
    lage = sprit_lage(stand)
    if lage is None:
        return L("Deinen Verbrauch kann ich dir nach der ersten vollen Runde sagen.", "I can tell you your consumption after the first full lap.")
    verbrauch = lage[0]
    anzahl = len(stand.messer.verbrauch_liste)
    if anzahl:
        return (L(f"Dein Verbrauch liegt bei {zahl(verbrauch, 2)} Litern pro Runde. "
                f"Das ist der Durchschnitt aus den letzten {runden_wort(anzahl)}.", f"Your consumption is {zahl(verbrauch, 2)} litres per lap. "
                f"That is the average of the last {runden_wort(anzahl)}."))
    return (L(f"ACC schätzt deinen Verbrauch auf {zahl(verbrauch, 2)} Liter pro Runde. "
            f"Ich messe ihn gerade noch selbst nach.", f"ACC estimates your consumption at {zahl(verbrauch, 2)} litres per lap. "
            f"I'm still measuring it myself."))


def antwort_spritsparen(stand):
    lage = sprit_lage(stand)
    if lage is None:
        return L("Das kann ich dir erst nach der ersten vollen Runde sagen.", "I can only tell you that after the first full lap.")
    verbrauch, restrunden, e = lage
    if restrunden is None or restrunden <= 0:
        return L("Ich kenne die Renndauer noch nicht, deshalb kann ich das noch nicht ausrechnen.", "I don't know the race length yet, so I can't calculate that yet.")
    if e["stopps"] == 0:
        return (L(f"Ja, du kommst ohne Stopp durch. Im Ziel hast du dann noch etwa "
                f"{zahl(e['ueberschuss'], 0)} Liter Reserve.", f"Yes, you can make it without a stop. You will have about "
                f"{zahl(e['ueberschuss'], 0)} litres in reserve at the finish."))
    reserve = acc_sprit.RESERVE_RUNDEN * verbrauch
    noetig = (stand.physik.tank - reserve) / restrunden
    if noetig <= 0:
        return L("Ohne Stopp geht es nicht mehr, der Tank ist dafür schon zu leer.", "Going without a stop is no longer possible, the tank is already too empty for that.")
    sparen = verbrauch - noetig
    prozent = sparen / verbrauch * 100
    text = (L(f"Ohne Stopp müsstest du deinen Verbrauch auf {zahl(noetig, 2)} Liter pro Runde senken. "
            f"Das sind {zahl(sparen, 2)} Liter oder {zahl(prozent, 0)} Prozent weniger als jetzt.", f"Without a stop you would have to lower your consumption to {zahl(noetig, 2)} litres per lap. "
            f"That is {zahl(sparen, 2)} litres or {zahl(prozent, 0)} percent less than now."))
    if prozent > 12:
        text += L(" Das ist kaum zu schaffen, plane lieber einen Stopp ein.", " That is hardly doable, better plan a stop.")
    else:
        text += L(" Mit Lift and Coast ist das machbar.", " That is doable with lift and coast.")
    return text


def dauer_finden(t):
    """'30 minuten' -> {'minuten': 30}, 'eine stunde' -> {'minuten': 60}, '20 runden' -> {'runden': 20}"""
    zahlen = {"eine": 1, "einer": 1, "ein": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6,
              "zehn": 10, "zwanzig": 20, "dreißig": 30, "vierzig": 40, "fünfzig": 50, "sechzig": 60,
              "fünfzehn": 15, "fünfundzwanzig": 25, "fünfundvierzig": 45, "neunzig": 90, "halbe": 0.5}
    muster = r"(\d+(?:[,.]\d+)?|" + "|".join(sorted(zahlen, key=len, reverse=True)) + r")\s*(minuten|minute|min|stunden|stunde|h|runden|runde)\b"
    treffer = re.search(muster, t)
    if not treffer:
        return None
    roh, einheit = treffer.group(1), treffer.group(2)
    wert = zahlen.get(roh)
    if wert is None:
        wert = float(roh.replace(",", "."))
    if einheit.startswith("stunde") or einheit == "h":
        return {"minuten": wert * 60}
    if einheit.startswith("min"):
        return {"minuten": wert}
    return {"runden": int(wert)}


def startsprit_berechnen(stand, dauer=None):
    """Wie viel Sprit braucht ein Rennen? Gibt dict oder (None, Grund) zurück.
    dauer: {'minuten': 30} oder {'runden': 20}; ohne Angabe die Länge des aktuellen Rennens."""
    g, s = stand.grafik, stand.statisch
    wissen = acc_gedaechtnis.holen(str(s.strecke), str(s.auto))
    verbrauch = stand.messer.verbrauch_schnitt() or (g.sprit_pro_runde if g.sprit_pro_runde > 0 else None) \
        or wissen.get("verbrauch")
    rundenzeit = stand.messer.rundenzeit_schnitt() or wissen.get("rundenzeit")
    if not rundenzeit and gueltige_zeit(g.i_beste_zeit):
        rundenzeit = g.i_beste_zeit / 1000 + 0.8
    if not verbrauch:
        return None, "verbrauch"
    runden = None
    minuten = None
    if dauer and dauer.get("runden"):
        runden = dauer["runden"]
    elif dauer and dauer.get("minuten"):
        minuten = dauer["minuten"]
    elif g.session == 2 and g.runden_fertig == 0:
        if g.runden_gesamt > 0:
            runden = g.runden_gesamt
        elif g.session_rest > 0:
            minuten = g.session_rest / 60000
    if runden is None and minuten is None:
        return None, "dauer"
    if runden is None:
        if not rundenzeit:
            return None, "rundenzeit"
        runden = math.ceil(minuten * 60 / rundenzeit)          # die angefangene Runde wird zu Ende gefahren
    reserve = acc_sprit.RESERVE_RUNDEN
    liter = math.ceil((runden + 1 + reserve) * verbrauch)      # +1 für die Formationsrunde
    tank_max = s.tank_max or 120
    return {"liter": liter, "runden": runden, "minuten": minuten, "verbrauch": verbrauch,
            "reserve": reserve, "tank_max": tank_max, "passt": liter <= tank_max}, None


def startsprit_text(stand, dauer=None, mit_tank=False, im_briefing=False):
    ergebnis, grund = startsprit_berechnen(stand, dauer)
    if ergebnis is None:
        return {"verbrauch": L("Dafür kenne ich deinen Verbrauch auf dieser Strecke noch nicht. Fahr erst ein paar "
                             "Runden, dann kann ich es dir genau sagen.", "I don't know your consumption on this track yet. Drive a few "
                             "laps first, then I can tell you exactly."),
                "dauer": L("Sag mir, wie lang das Rennen ist, zum Beispiel: Wie viel Sprit für 30 Minuten?", "Tell me how long the race is, for example: how much fuel for 30 minutes?"),
                "rundenzeit": L("Dafür brauche ich erst eine gefahrene Runde, damit ich weiß, wie viele Runden das werden.", "I need one completed lap first, so I know how many laps that will be.")
                }[grund]
    e = ergebnis
    laenge = (L(f"{zahl(e['minuten'], 0)} Minuten", f"{zahl(e['minuten'], 0)} minutes") if e["minuten"] else L(f"{e['runden']} Runden", f"{e['runden']} laps"))
    text = (L(f"{'Dafür' if im_briefing else 'Für ' + laenge} brauchst du ungefähr {e['liter']} Liter. Das sind etwa {e['runden']} Runden "
            f"bei {zahl(e['verbrauch'])} Litern pro Runde, plus Formationsrunde und Reserve.", f"{'For that' if im_briefing else 'For ' + laenge} you need about {e['liter']} litres. That is about {e['runden']} laps "
            f"at {zahl(e['verbrauch'])} litres per lap, plus formation lap and reserve."))
    if not e["passt"]:
        text += (L(f" Das passt nicht in den Tank, der fasst nur {zahl(e['tank_max'], 0)} Liter. "
                 f"Fahr voll los und plan einen Boxenstopp ein.", f" That doesn't fit in the tank, it only holds {zahl(e['tank_max'], 0)} litres. "
                 f"Start full and plan a pit stop."))
    elif mit_tank:
        tank = stand.physik.tank
        if tank < e["liter"] - e["verbrauch"] * 0.5:
            text += (L(f" Du hast gerade {zahl(tank, 0)} Liter im Tank, das reicht nicht ganz. "
                     f"Du wirst einmal nachtanken müssen.", f" You have {zahl(tank, 0)} litres in the tank right now, that's not quite enough. "
                     f"You will have to refuel once."))
        elif tank > e["liter"] + e["verbrauch"] * 2:
            text += (L(f" Du hast {zahl(tank, 0)} Liter drin, also {zahl(tank - e['liter'], 0)} Liter mehr als nötig. "
                     f"Beim nächsten Mal kannst du leichter starten.", f" You have {zahl(tank, 0)} litres in, so {zahl(tank - e['liter'], 0)} litres more than needed. "
                     f"Next time you can start lighter."))
        else:
            text += L(f" Mit deinen {zahl(tank, 0)} Litern passt das genau.", f" With your {zahl(tank, 0)} litres that fits exactly.")
    return text


def antwort_startsprit(stand, dauer=None):
    return startsprit_text(stand, dauer, mit_tank=stand.grafik.session == 2 and not dauer)


DRUCK_FENSTER = {"trocken": (26.0, 27.0), "regen": (29.5, 31.0)}


def druck_empfehlung(stand):
    """Wie sollte der Reifendruck für den nächsten Stint geändert werden?
    Gibt (liste mit Änderung je Rad in PSI, art) zurück, oder None, wenn es keine Daten gibt."""
    g = stand.grafik
    runden = [r for r in stand.protokoll.runden if r.get("druck") and r["gueltig"] and not r["box"]][-3:]
    if len(runden) < 2:
        return None
    regen = "wet" in str(g.reifen_mischung).lower() or bool(g.regenreifen)
    tief, hoch = DRUCK_FENSTER["regen" if regen else "trocken"]
    ziel = (tief + hoch) / 2
    schnitt = [sum(r["druck"][i] for r in runden) / len(runden) for i in range(4)]
    aenderung = []
    for wert in schnitt:
        if tief <= wert <= hoch:
            aenderung.append(0.0)
        else:
            aenderung.append(round((ziel - wert) * 10) / 10)
    return aenderung, schnitt, ("regen" if regen else "trocken")


def druck_text(stand, kurz=False):
    ergebnis = druck_empfehlung(stand)
    if ergebnis is None:
        return None
    aenderung, schnitt, art = ergebnis
    teile = []
    for rad, wert in zip(RAEDER, aenderung):
        if abs(wert) >= 0.2:
            teile.append(L(f"{rad} {zahl(abs(wert))} PSI {'weniger' if wert < 0 else 'mehr'}", f"{rad} {zahl(abs(wert))} PSI {'less' if wert < 0 else 'more'}"))
    if not teile:
        return None if kurz else (L("Deine Reifendrücke liegen alle im idealen Bereich, warm zwischen "
                                  f"{zahl(DRUCK_FENSTER[art][0], 0)} und {zahl(DRUCK_FENSTER[art][1], 0)} PSI. Lass sie so.", "Your tyre pressures are all in the ideal range, hot between "
                                  f"{zahl(DRUCK_FENSTER[art][0], 0)} and {zahl(DRUCK_FENSTER[art][1], 0)} PSI. Leave them as they are."))
    text = L("Für den nächsten Stint stell den Reifendruck im Boxenmenü so ein: ", "For the next stint, set the tyre pressures in the pit menu like this: ") + ", ".join(teile[:-1])
    text += (L(" und ", " and ") + teile[-1] if len(teile) > 1 else teile[0]) + "."
    if not kurz:
        text += (L(f" Ideal sind warm {zahl(DRUCK_FENSTER[art][0], 0)} bis {zahl(DRUCK_FENSTER[art][1], 0)} PSI, "
                 f"gemessen über deine letzten Runden.", f" Ideal is {zahl(DRUCK_FENSTER[art][0], 0)} to {zahl(DRUCK_FENSTER[art][1], 0)} PSI hot, "
                 f"measured over your last laps."))
    return text


def antwort_druck_anpassen(stand):
    return druck_text(stand) or (L("Dafür brauche ich noch zwei saubere Runden mit warmen Reifen. "
                                 "Frag mich danach noch einmal.", "I need two more clean laps on warm tyres for that. "
                                 "Ask me again after that."))


def antwort_box_jetzt(stand):
    """Der Fahrer ist (gleich) in der Box: Was ist jetzt zu tun?"""
    g = stand.grafik
    lage = sprit_lage(stand)
    teile = []
    if g.in_boxengasse or g.in_box:
        teile.append(L("Copy, du bist in der Box.", "Copy, you are in the pits."))
    else:
        teile.append(L("Copy, komm rein.", "Copy, box this lap."))
    if not stand.physik.pitlimiter and not g.in_box:
        teile.append(L("Denk an den Pitlimiter.", "Remember the pit limiter."))
    if lage and lage[1] is not None:
        e = lage[2]
        if e["stopps"] >= 1:
            teile.append(L(f"Wir tanken {e['menge_pro_stopp']} Liter, damit kommst du ", f"We refuel {e['menge_pro_stopp']} litres, that gets you ")
                         + (L("bis ins Ziel.", "to the finish.") if e["stopps"] == 1 else L("bis zum nächsten Stopp.", "to the next stop.")))
            teile.append(boxenmenue_hinweis(stand, e["menge_pro_stopp"]).strip()
                         or L("Das Boxenmenü ist richtig eingestellt.", "The pit menu is set correctly."))
        else:
            teile.append(L(f"Sprit brauchst du keinen, der reicht bis ins Ziel. Stell im Boxenmenü null Liter ein, "
                         f"das spart Zeit.", f"You don't need any fuel, it lasts to the finish. Set zero litres in the pit menu, "
                         f"that saves time."))
    elif lage:
        teile.append(L("Wie viel Sprit wir brauchen, kann ich erst sagen, wenn ich die Renndauer kenne.", "I can only tell you how much fuel we need once I know the race length."))
    druck = druck_text(stand, kurz=True)
    if druck:
        teile.append(druck)
    if any(x > 0.05 for x in stand.physik.schaden):
        teile.append(L("Du hast Schaden am Auto, lass ihn im Boxenmenü reparieren.", "You have damage on the car, have it repaired in the pit menu."))
    fehlend = g.fehlende_pflichtstopps
    if 0 < fehlend < 10:
        teile.append(L("Damit ist auch der Pflichtstopp erledigt.", "That also takes care of the mandatory stop."))
    if stand.acc.verbindungs_id is not None and not (g.in_boxengasse or g.in_box):
        rauskommen = antwort_rauskommen(stand)
        teile.append(rauskommen.split(". ", 1)[-1])
    return " ".join(t for t in teile if t)


def antwort_box(stand):
    lage = sprit_lage(stand)
    if lage is None:
        return L("Für die Boxenstrategie brauche ich erst eine volle Runde mit Verbrauchsmessung.", "For the pit strategy I first need one full lap with fuel measurement.")
    verbrauch, restrunden, e = lage
    if restrunden is None:
        return L("Ich kenne die Renndauer noch nicht, deshalb kann ich die Strategie noch nicht rechnen.", "I don't know the race length yet, so I can't calculate the strategy yet.")
    if e["stopps"] == 0:
        text = (L(f"Du musst nicht an die Box, der Sprit reicht bis ins Ziel. "
                f"Am Ende bleiben ungefähr {zahl(e['ueberschuss'], 0)} Liter übrig.", f"You don't need to pit, the fuel lasts to the finish. "
                f"You will have about {zahl(e['ueberschuss'], 0)} litres left at the end."))
    elif e["stopps"] == 1:
        if e["fenster_von"] > e["fenster_bis"] or e["aktuelle_runde"] > e["fenster_bis"]:
            return (L(f"Der Sprit wird knapp! Komm so bald wie möglich an die Box und tanke "
                    f"{e['menge_pro_stopp']} Liter nach.", f"Fuel is getting critical! Box as soon as possible and add "
                    f"{e['menge_pro_stopp']} litres."))
        text = L(f"Du musst einmal an die Box und dabei {e['menge_pro_stopp']} Liter nachtanken.", f"You need to pit once and add {e['menge_pro_stopp']} litres.")
        if e["aktuelle_runde"] >= e["fenster_von"]:
            text += (L(f" Das Boxenfenster ist jetzt offen, du solltest spätestens in Runde "
                     f"{e['fenster_bis']} reinkommen.", f" The pit window is open now, you should come in by lap "
                     f"{e['fenster_bis']} at the latest."))
        else:
            text += L(f" Das Boxenfenster geht von Runde {e['fenster_von']} bis Runde {e['fenster_bis']}.", f" The pit window is from lap {e['fenster_von']} to lap {e['fenster_bis']}.")
        text += boxenmenue_hinweis(stand, e["menge_pro_stopp"])
    else:
        text = (L(f"Du musst {e['stopps']} Mal an die Box und jedes Mal etwa {e['menge_pro_stopp']} Liter "
                f"nachtanken. Der erste Stopp sollte spätestens in Runde {e['fenster_bis']} sein.", f"You need to pit {e['stopps']} times and add about {e['menge_pro_stopp']} litres each time. "
                f"The first stop should be by lap {e['fenster_bis']} at the latest."))
    fehlend = stand.grafik.fehlende_pflichtstopps
    if 0 < fehlend < 10:
        text += (L(" Achtung, du hast außerdem noch ", " Attention, you also still have ")
                 + (L("einen Pflichtstopp", "one mandatory stop") if fehlend == 1 else L(f"{fehlend} Pflichtstopps", f"{fehlend} mandatory stops")) + L(" offen.", " to do."))
    return text


def boxenmenue_hinweis(stand, menge):
    eingestellt = stand.grafik.mfd_sprit
    if abs(eingestellt - menge) >= 2:
        return (L(f" Im Boxenmenü sind gerade {zahl(eingestellt, 0)} Liter eingestellt, "
                f"bitte stell dort {menge} Liter ein.", f" The pit menu is currently set to {zahl(eingestellt, 0)} litres, "
                f"please set it to {menge} litres."))
    return ""


def antwort_position(stand):
    platz = stand.acc.mein_platz()
    if platz is None:
        return L(f"Du liegst auf Platz {stand.grafik.position}.", f"You are in P{stand.grafik.position}.")
    return L(f"Du liegst auf Platz {platz} von {len(stand.acc.rangliste())}.", f"You are in P{platz} of {len(stand.acc.rangliste())}.")


def antwort_runde(stand):
    g = stand.grafik
    runde = g.runden_fertig + 1
    if g.runden_gesamt > 0:
        return L(f"Du fährst gerade Runde {runde} von {g.runden_gesamt}.", f"You are on lap {runde} of {g.runden_gesamt}.")
    return L(f"Du fährst gerade Runde {runde}.", f"You are on lap {runde}.")


def antwort_rundenzeit(stand):
    g = stand.grafik
    teile = []
    if gueltige_zeit(g.i_letzte_zeit):
        teile.append(L(f"Deine letzte Runde bist du in {zeit_sprechen(g.i_letzte_zeit)} gefahren.", f"Your last lap was {zeit_sprechen(g.i_letzte_zeit)}."))
    if gueltige_zeit(g.i_beste_zeit):
        teile.append(L(f"Deine Bestzeit liegt bei {zeit_sprechen(g.i_beste_zeit)}.", f"Your best lap is {zeit_sprechen(g.i_beste_zeit)}."))
    if not teile:
        return L("Du hast noch keine gezeitete Runde.", "You don't have a timed lap yet.")
    return " ".join(teile)


def antwort_delta(stand):
    g = stand.grafik
    if not gueltige_zeit(g.i_beste_zeit):
        return L("Du hast noch keine Bestzeit, deshalb gibt es noch kein Delta.", "You don't have a best lap yet, so there is no delta yet.")
    delta = g.i_delta / 1000
    if abs(delta) < 0.05:
        text = L("Du liegst in dieser Runde genau auf deiner Bestzeit.", "You are exactly on your best lap this lap.")
    elif delta < 0:
        text = L(f"Du bist in dieser Runde {sekunden_sprechen(-delta)} schneller als deine Bestzeit.", f"You are {sekunden_sprechen(-delta)} faster than your best lap this lap.")
    else:
        text = L(f"Du bist in dieser Runde {sekunden_sprechen(delta)} langsamer als deine Bestzeit.", f"You are {sekunden_sprechen(delta)} slower than your best lap this lap.")
    if gueltige_zeit(g.i_geschaetzte_zeit):
        text += L(f" Hochgerechnet wird das eine {zeit_sprechen(g.i_geschaetzte_zeit)}.", f" Projected, that is a {zeit_sprechen(g.i_geschaetzte_zeit)} lap.")
    if not g.runde_gueltig:
        text += L(" Die Runde ist allerdings ungültig.", " But the lap is invalid.")
    return text


def antwort_rest(stand):
    g = stand.grafik
    if g.runden_gesamt > 0:
        rest = g.runden_gesamt - g.runden_fertig
        return (L("Das ist die letzte Runde.", "This is the last lap.") if rest <= 1
                else L(f"Es sind noch {runden_wort(rest)} zu fahren.", f"There are {runden_wort(rest)} to go."))
    if g.session_rest <= 0:
        return L("Die Zeit ist abgelaufen, das ist die letzte Runde.", "Time is up, this is the last lap.")
    minuten = int(g.session_rest / 60000)
    text = (L(f"Das Rennen geht noch {minuten} {'Minute' if minuten == 1 else 'Minuten'}.", f"The race has {minuten} {'minute' if minuten == 1 else 'minutes'} to go.") if minuten
            else L("Das Rennen geht noch weniger als eine Minute.", "Less than a minute of the race to go."))
    lage = sprit_lage(stand)
    if lage and lage[1] is not None:
        text += L(f" Das sind ungefähr {zahl(lage[1], 0)} Runden.", f" That is about {zahl(lage[1], 0)} laps.")
    return text


def antwort_reifendruck(stand):
    druck = list(stand.physik.reifendruck)
    if not any(druck):
        return L("Ich bekomme gerade keine Reifendrücke.", "I'm not getting any tyre pressures right now.")
    w = [zahl(x) for x in druck]
    text = (L(f"Der Reifen vorne links hat {w[0]} PSI, vorne rechts {w[1]} PSI, "
            f"hinten links {w[2]} PSI und hinten rechts {w[3]} PSI.", f"Front left is at {w[0]} PSI, front right {w[1]} PSI, "
            f"rear left {w[2]} PSI and rear right {w[3]} PSI."))
    empfehlung = druck_text(stand, kurz=True)
    if empfehlung:
        text += " " + empfehlung
    return text


def antwort_reifentemp(stand):
    temp = list(stand.physik.reifen_kerntemp)
    if not any(temp):
        return L("Ich bekomme gerade keine Reifentemperaturen.", "I'm not getting any tyre temperatures right now.")
    w = [zahl(x, 0) for x in temp]
    return (L(f"Die Reifentemperatur beträgt vorne links {w[0]} Grad, vorne rechts {w[1]} Grad, "
            f"hinten links {w[2]} Grad und hinten rechts {w[3]} Grad.", f"Tyre temperatures are front left {w[0]} degrees, front right {w[1]} degrees, "
            f"rear left {w[2]} degrees and rear right {w[3]} degrees."))


def antwort_reifenart(stand):
    g = stand.grafik
    art = L("Regenreifen", "wet tyres") if "wet" in g.reifen_mischung.lower() or g.regenreifen else L("Trockenreifen", "slicks")
    text = L(f"Du fährst gerade auf {art}", f"You are currently on {art}")
    if g.reifensatz > 0:
        text += L(f", das ist Reifensatz {g.reifensatz}", f", that is tyre set {g.reifensatz}")
    return text + "."


def antwort_reifen(stand):
    return antwort_reifenart(stand) + " " + antwort_reifendruck(stand) + " " + antwort_reifentemp(stand)


def antwort_bremsbelag(stand):
    belag = list(stand.physik.belag)
    if not any(belag):
        return L("Ich bekomme gerade keine Werte zu den Bremsbelägen.", "I'm not getting any brake pad values right now.")
    vorne, hinten = min(belag[0], belag[1]), min(belag[2], belag[3])
    text = (L(f"Die vorderen Bremsbeläge haben noch {zahl(vorne)} Millimeter, "
            f"die hinteren noch {zahl(hinten)} Millimeter.", f"The front brake pads have {zahl(vorne)} millimetres left, "
            f"the rears {zahl(hinten)} millimetres."))
    if min(vorne, hinten) < 12:
        text += L(" Die werden langsam dünn.", " They are getting thin.")
    return text


def antwort_bremstemp(stand):
    temp = list(stand.physik.brems_temp)
    if not any(temp):
        return L("Ich bekomme gerade keine Bremstemperaturen.", "I'm not getting any brake temperatures right now.")
    vorne, hinten = (temp[0] + temp[1]) / 2, (temp[2] + temp[3]) / 2
    return (L(f"Die vorderen Bremsen haben {zahl(vorne, 0)} Grad "
            f"und die hinteren Bremsen {zahl(hinten, 0)} Grad.", f"The front brakes are at {zahl(vorne, 0)} degrees "
            f"and the rear brakes at {zahl(hinten, 0)} degrees."))


def antwort_wetter(stand):
    g, p = stand.grafik, stand.physik
    jetzt = REGEN_JETZT[g.regen] if 0 <= g.regen < 6 else L("ist das Wetter unbekannt", "the weather is unknown")
    in10 = REGEN_SPAETER[g.regen_10min] if 0 <= g.regen_10min < 6 else L("ist es unklar", "it is unclear")
    in30 = REGEN_SPAETER[g.regen_30min] if 0 <= g.regen_30min < 6 else L("ist es unklar", "it is unclear")
    if g.regen == g.regen_10min == g.regen_30min:
        text = L(f"Aktuell {jetzt}, und das bleibt auch die nächsten 30 Minuten so.", f"Right now {jetzt}, and it stays that way for the next 30 minutes.")
    else:
        text = L(f"Aktuell {jetzt}. In 10 Minuten {in10}, und in 30 Minuten {in30}.", f"Right now {jetzt}. In 10 minutes {in10}, and in 30 minutes {in30}.")
    text += (L(f" Die Lufttemperatur beträgt {zahl(p.luft_temp, 0)} Grad "
             f"und die Streckentemperatur {zahl(p.strecken_temp, 0)} Grad.", f" Air temperature is {zahl(p.luft_temp, 0)} degrees "
             f"and track temperature {zahl(p.strecken_temp, 0)} degrees."))
    return text


def antwort_temperaturen(stand):
    p = stand.physik
    return (L(f"Die Lufttemperatur beträgt {zahl(p.luft_temp, 0)} Grad "
            f"und die Streckentemperatur {zahl(p.strecken_temp, 0)} Grad.", f"Air temperature is {zahl(p.luft_temp, 0)} degrees "
            f"and track temperature {zahl(p.strecken_temp, 0)} degrees."))


def antwort_grip(stand):
    g = stand.grafik
    if 0 <= g.grip_status < len(GRIP_SAETZE):
        return GRIP_SAETZE[g.grip_status]
    return L("Den Zustand der Strecke kenne ich gerade nicht.", "I don't know the track condition right now.")


def antwort_wind(stand):
    g = stand.grafik
    return L(f"Der Wind weht mit etwa {zahl(g.wind_tempo * 3.6, 0)} Kilometern pro Stunde.", f"The wind is blowing at about {zahl(g.wind_tempo * 3.6, 0)} kilometres per hour.")


def antwort_wassertemp(stand):
    return L(f"Die Wassertemperatur des Motors beträgt {zahl(stand.physik.wasser_temp, 0)} Grad.", f"Engine water temperature is {zahl(stand.physik.wasser_temp, 0)} degrees.")


def antwort_schaden(stand):
    werte = list(stand.physik.schaden)
    zonen = [SCHADEN_ZONEN[i] for i, w in enumerate(werte) if w > 0.01]
    if not zonen:
        return L("Dein Auto hat keinen Schaden.", "Your car has no damage.")
    if len(zonen) == 1:
        return L(f"Dein Auto hat Schaden {zonen[0]}.", f"Your car has damage at the {zonen[0]}.")
    return L(f"Dein Auto hat Schaden {', '.join(zonen[:-1])} und {zonen[-1]}.", f"Your car has damage at the {', '.join(zonen[:-1])} and {zonen[-1]}.")


def antwort_elektronik(stand):
    g = stand.grafik
    return (L(f"Die Traktionskontrolle steht auf Stufe {g.tc}, der TC-Cut auf Stufe {g.tc_cut}, "
            f"das ABS auf Stufe {g.abs} und die Motor-Map auf Stufe {g.motor_map}.", f"Traction control is on {g.tc}, TC cut on {g.tc_cut}, "
            f"ABS on {g.abs} and the engine map on {g.motor_map}."))


def antwort_stint(stand):
    rest = stand.grafik.fahrer_stint_rest
    if rest <= 0 or rest > 50 * 3600 * 1000:
        return L("Für deinen Stint gibt es kein Zeitlimit.", "There is no time limit for your stint.")
    minuten = int(rest / 60000)
    return L(f"Dein Stint dauert noch {minuten} {'Minute' if minuten == 1 else 'Minuten'}.", f"Your stint has {minuten} {'minute' if minuten == 1 else 'minutes'} left.")


def antwort_uhrzeit(stand):
    sekunden = int(stand.grafik.uhrzeit) % 86400
    return L(f"Im Spiel ist es gerade {sekunden // 3600} Uhr {sekunden % 3600 // 60}.", f"In the game it is currently {sekunden // 3600}:{sekunden % 3600 // 60:02d}.")


def antwort_strafe(stand):
    g = stand.grafik
    if g.strafe == 0:
        return L("Du hast keine offene Strafe.", "You have no open penalty.")
    return strafe_text(g.strafe)


def antwort_flagge(stand):
    return FLAGGEN_NAMEN.get(stand.grafik.flagge, L("Welche Flagge gerade draußen ist, weiß ich nicht.", "I don't know which flag is out right now."))


def antwort_gueltig(stand):
    if stand.grafik.runde_gueltig:
        return L("Deine aktuelle Runde ist gültig.", "Your current lap is valid.")
    return L("Deine aktuelle Runde ist ungültig, weil du die Track Limits verletzt hast.", "Your current lap is invalid because you exceeded track limits.")


def antwort_pflichtstopp(stand):
    g = stand.grafik
    if 0 < g.fehlende_pflichtstopps < 10:
        n = g.fehlende_pflichtstopps
        return L(f"Du musst noch {'einen Pflichtstopp' if n == 1 else f'{n} Pflichtstopps'} machen.", f"You still have to do {'one mandatory stop' if n == 1 else f'{n} mandatory stops'}.")
    if g.pflichtstopp_erledigt:
        return L("Dein Pflichtstopp ist erledigt.", "Your mandatory stop is done.")
    return L("Es ist kein Pflichtstopp offen.", "There is no mandatory stop open.")


def antwort_lagebericht(stand):
    acc, g = stand.acc, stand.grafik
    teile = []
    platz = acc.mein_platz()
    if platz:
        teile.append(L(f"Du liegst auf Platz {platz}.", f"You are in P{platz}."))
        if acc.ist_rennen():
            vorne = hinten = None
            if platz > 1:
                vorne = abstand_kurz(*acc.abstand_zu(acc.auto_auf_platz(platz - 1)))
            hinten_auto = acc.auto_auf_platz(platz + 1)
            if hinten_auto:
                hinten = abstand_kurz(*acc.abstand_zu(hinten_auto))
            if vorne and hinten:
                teile.append(L(f"Der Abstand zum Vordermann beträgt {vorne}, "
                             f"und der Hintermann ist {hinten} hinter dir.", f"The gap to the car ahead is {vorne}, "
                             f"and the car behind is {hinten} behind you."))
            elif vorne:
                teile.append(L(f"Der Abstand zum Vordermann beträgt {vorne}.", f"The gap to the car ahead is {vorne}."))
            elif hinten:
                teile.append(L(f"Der Hintermann ist {hinten} hinter dir.", f"The car behind is {hinten} behind you."))
    lage = sprit_lage(stand)
    if lage:
        _, restrunden, e = lage
        satz = L(f"Dein Sprit reicht noch für {zahl(e['reicht_runden'])} Runden", f"Your fuel lasts for {zahl(e['reicht_runden'])} more laps")
        if restrunden is not None:
            satz += (L(", das reicht bis ins Ziel.", ", that gets you to the finish.") if e["stopps"] == 0
                     else L(f", beim Stopp brauchen wir noch {e['menge_pro_stopp']} Liter.", f", at the stop we need {e['menge_pro_stopp']} more litres."))
        else:
            satz += "."
        teile.append(satz)
    teile.append(antwort_rest(stand).split(L(" Das sind", " That is"))[0])
    if g.strafe:
        teile.append(L("Außerdem hast du noch eine offene Strafe.", "You also have an open penalty."))
    return mit_zuspruch(" ".join(teile), stand, wahrscheinlichkeit=0.8)


# ---------------------------------------------------------------------------
# Zuspruch: ein taktischer oder motivierender Satz, passend zur Lage
# ---------------------------------------------------------------------------
ZUSPRUCH = L({
    "fuehrung": [
        "Du führst, halt den Rhythmus und bring es sauber nach Hause.",
        "Starke Arbeit an der Spitze, konzentrier dich einfach auf saubere Runden.",
        "Keine Hektik, du bestimmst das Tempo da vorne.",
    ],
    "sandwich": [
        "Vorne und hinten ist es eng, bleib sauber und mach keine Fehler.",
        "Du steckst mitten im Kampf, konzentrier dich auf deine Linie und lass dich nicht stressen.",
        "Das ist ein enges Paket, jetzt zählt jeder saubere Kurvenausgang.",
    ],
    "verteidigen": [
        "{hinten} macht Druck, konzentrier dich auf saubere Kurvenausgänge.",
        "Lass dich von {hinten_dat} nicht nervös machen, fahr deine Linie und mach die Tür beim Bremsen zu.",
        "{hinten} ist dicht dran, bleib ruhig und vermeide Fehler, dann kommt er nicht vorbei.",
    ],
    "angreifen": [
        "Du bist in Schlagdistanz zu {vorne_dat}, such dir die Lücke beim Anbremsen.",
        "{vorne} ist direkt vor dir, bleib im Windschatten und warte auf deine Chance.",
        "Jetzt ist der Moment, setz {vorne_akk} unter Druck, aber bleib clever.",
    ],
    "aufholen": [
        "Du bist schneller als {vorne}, bleib dran, der kommt in Reichweite.",
        "Du holst auf {vorne_akk} auf, mach weiter so.",
        "Die Pace stimmt, {vorne} wird gleich in Reichweite sein.",
    ],
    "fokus_vorne": [
        "Nach hinten hast du genug Abstand, konzentrier dich auf {vorne_akk}.",
        "Hinter dir ist alles ruhig, dein Ziel ist jetzt {vorne}.",
        "Vergiss den Rückspiegel, konzentrier dich ganz auf {vorne_akk} vor dir.",
    ],
    "fokus_hinten": [
        "Nach vorne ist es weit, konzentrier dich darauf, {hinten_akk} hinter dir zu halten.",
        "{vorne} ist gerade außer Reichweite, pass lieber auf {hinten_akk} hinter dir auf.",
        "Sichere den Platz gegen {hinten_akk}, nach vorne geht gerade nicht viel.",
    ],
    "allein": [
        "Du hast nach vorne und hinten genug Abstand, fahr dein eigenes Tempo.",
        "Gerade ist niemand in der Nähe, konzentrier dich auf saubere und konstante Runden.",
        "Ruhige Phase, nutz sie, um deinen Rhythmus zu finden.",
    ],
}, {
    "fuehrung": [
        "You're leading, keep the rhythm and bring it home cleanly.",
        "Great work at the front, just focus on clean laps.",
        "No rush, you're setting the pace up there.",
    ],
    "sandwich": [
        "It's tight in front and behind, stay clean and don't make mistakes.",
        "You're right in the middle of the fight, focus on your line and don't get stressed.",
        "It's a tight pack, every clean corner exit counts now.",
    ],
    "verteidigen": [
        "{hinten} is pushing, focus on clean corner exits.",
        "Don't let {hinten_dat} make you nervous, drive your line and close the door on the brakes.",
        "{hinten} is close, stay calm and avoid mistakes, then he won't get past.",
    ],
    "angreifen": [
        "You're within striking distance of {vorne_dat}, look for the gap under braking.",
        "{vorne} is right in front of you, stay in the slipstream and wait for your chance.",
        "Now is the moment, put {vorne_akk} under pressure, but stay smart.",
    ],
    "aufholen": [
        "You're faster than {vorne}, stay on it, you'll be in range soon.",
        "You're catching {vorne_akk}, keep it up.",
        "The pace is right, {vorne} will be in range soon.",
    ],
    "fokus_vorne": [
        "You have enough gap behind, focus on {vorne_akk}.",
        "It's all quiet behind you, your target now is {vorne}.",
        "Forget the mirrors, focus fully on {vorne_akk} ahead of you.",
    ],
    "fokus_hinten": [
        "It's a long way to the car ahead, focus on keeping {hinten_akk} behind you.",
        "{vorne} is out of reach right now, better keep an eye on {hinten_akk} behind you.",
        "Secure the position against {hinten_akk}, not much is possible ahead right now.",
    ],
    "allein": [
        "You have enough gap ahead and behind, drive your own pace.",
        "Nobody is close right now, focus on clean and consistent laps.",
        "Quiet phase, use it to find your rhythm.",
    ],
})
_zuletzt_gesagt = []


def _abstand_sekunden(acc, auto):
    art, wert = acc.abstand_zu(auto)
    return abs(wert) if art == "sek" and wert is not None else None


def zuspruch(stand, immer=False, wahrscheinlichkeit=0.6):
    """Ein passender taktischer oder motivierender Satz, oder "".
    Kommt nur manchmal (wahrscheinlichkeit), außer immer=True. Wiederholt sich nicht direkt."""
    acc = stand.acc
    if not immer and random.random() > wahrscheinlichkeit:
        return ""
    if acc.verbindungs_id is None or not acc.ist_rennen():
        return ""
    platz = acc.mein_platz()
    if not platz:
        return ""
    ich = acc.ich()
    vorne_auto = acc.auto_auf_platz(platz - 1) if platz > 1 else None
    hinten_auto = acc.auto_auf_platz(platz + 1)
    vorne = _abstand_sekunden(acc, vorne_auto) if vorne_auto else None
    hinten = _abstand_sekunden(acc, hinten_auto) if hinten_auto else None
    schneller_als_vorne = (vorne_auto is not None and ich is not None
                           and gueltige_zeit(vorne_auto.letzte_runde) and gueltige_zeit(ich.letzte_runde)
                           and ich.letzte_runde < vorne_auto.letzte_runde - 100)

    if platz == 1 and (hinten is None or hinten > 1.0):
        lage = "fuehrung"
    elif vorne is not None and hinten is not None and vorne < 1.0 and hinten < 1.0:
        lage = "sandwich"
    elif hinten is not None and hinten < 1.0:
        lage = "verteidigen"
    elif vorne is not None and vorne < 1.0:
        lage = "angreifen"
    elif vorne is not None and vorne < 4.0 and schneller_als_vorne:
        lage = "aufholen"
    elif vorne is not None and hinten is not None and vorne > 4.0 and hinten > 4.0:
        lage = "allein"
    elif vorne is not None and (hinten is None or hinten > vorne * 2):
        lage = "fokus_vorne"
    elif hinten is not None and vorne is not None and vorne > hinten * 2 and hinten < 3.0:
        lage = "fokus_hinten"
    elif platz == 1:
        lage = "verteidigen" if hinten is not None and hinten < 1.0 else "fuehrung"
    else:
        return ""

    namen = {}
    for schluessel, auto, ersatz in (("vorne", vorne_auto, L("Vordermann", "car ahead")), ("hinten", hinten_auto, L("Hintermann", "car behind"))):
        for fall, artikel, endung in (("nom", "der", ""), ("dat", "dem", "_dat"), ("akk", "den", "_akk")):
            namen[schluessel + endung] = name_von(auto, fall) if auto else L(f"{artikel} {ersatz}", f"the {ersatz}")
    moeglich = [satz for satz in ZUSPRUCH[lage] if satz not in _zuletzt_gesagt] or ZUSPRUCH[lage]
    satz = random.choice(moeglich)
    _zuletzt_gesagt.append(satz)
    del _zuletzt_gesagt[:-6]                      # die letzten sechs Sätze nicht wiederholen
    return gross(satz.format(**namen))


FAHRER_NAME = ""          # wird vom Fenster gesetzt, z. B. "Lutz"


def mit_zuspruch(text, stand, **optionen):
    extra = zuspruch(stand, **optionen)
    if extra and FAHRER_NAME and extra[-1] in ".!" and random.random() < 0.3:
        extra = f"{extra[:-1]}, {FAHRER_NAME}{extra[-1]}"      # "... bleib dran, Lutz."
    return f"{text} {extra}" if extra else text


SEKTOR_NAMEN = L({1: "ersten", 2: "zweiten", 3: "dritten"}, {1: "first", 2: "second", 3: "third"})


def _kleinzeit(sekunden):
    """0,3 -> 'drei Zehntel', 1,2 -> '1,2 Sekunden'."""
    if abs(sekunden) >= 0.95:
        return sekunden_sprechen(abs(sekunden))
    zehntel = round(abs(sekunden) * 10)
    if englisch():
        if zehntel == 0:
            return f"{round(abs(sekunden) * 100)} hundredths"
        return "one tenth" if zehntel == 1 else f"{zehntel} tenths"
    if zehntel == 0:
        return f"{round(abs(sekunden) * 100)} Hundertstel"
    return {1: "ein Zehntel", 2: "zwei Zehntel", 3: "drei Zehntel", 4: "vier Zehntel", 5: "fünf Zehntel",
            6: "sechs Zehntel", 7: "sieben Zehntel", 8: "acht Zehntel", 9: "neun Zehntel"}[zehntel]


def antwort_sektoren(stand, ziel=None):
    """Wo verlierst du Zeit? Ohne Ziel: gegen deine eigenen besten Sektoren.
    Mit Ziel (z. B. Vordermann): gegen dessen letzte Runde."""
    acc = stand.acc
    ich = acc.ich()
    if ich is None or not ich.letzte_sektoren or not all(ich.letzte_sektoren):
        return L("Ich habe noch keine Sektorzeiten von dir. Fahr erst eine ganze Runde.", "I don't have any sector times from you yet. Do a full lap first.")
    meine = ich.letzte_sektoren
    if ziel is not None:
        platz, auto, fehler = auto_finden(stand, ziel)
        if fehler:
            return fehler
        if not auto.letzte_sektoren or not all(auto.letzte_sektoren):
            return L(f"Von {name_von(auto, 'dat')} habe ich noch keine Sektorzeiten.", f"I don't have any sector times from {name_von(auto, 'dat')} yet.")
        vergleich, wer = auto.letzte_sektoren, L(f"{name_von(auto, 'dat', mit_platz=False)} auf Platz {platz}", f"{name_von(auto, 'dat', mit_platz=False)} in P{platz}")
    else:
        vergleich = stand.protokoll.beste_sektoren() if stand.protokoll.runden else []
        if len(vergleich) < len(meine) or not all(vergleich[:len(meine)]):
            vergleich = ich.beste_sektoren
        if not vergleich or not all(vergleich):
            return L("Ich habe noch keine Bestzeiten in den Sektoren von dir.", "I don't have any best sector times from you yet.")
        wer = L("deinen besten Sektoren", "your best sectors")
    unterschiede = [((m - v) / 1000) for m, v in zip(meine, vergleich)]
    teile = []
    for nummer, wert in enumerate(unterschiede, start=1):
        sektor = SEKTOR_NAMEN.get(nummer, f"{nummer}.")
        if wert > 0.05:
            teile.append(L(f"im {sektor} Sektor {_kleinzeit(wert)} langsamer", f"{_kleinzeit(wert)} slower in the {sektor} sector"))
        elif wert < -0.05:
            teile.append(L(f"im {sektor} Sektor {_kleinzeit(wert)} schneller", f"{_kleinzeit(wert)} faster in the {sektor} sector"))
        else:
            teile.append(L(f"im {sektor} Sektor gleich schnell", f"equally fast in the {sektor} sector"))
    text = L(f"In deiner letzten Runde warst du im Vergleich zu {wer} ", f"On your last lap, compared to {wer}, you were ") + ", ".join(teile[:-1])
    text += L(f" und {teile[-1]}.", f" and {teile[-1]}.") if len(teile) > 1 else f"{teile[0]}."
    schlecht = max(range(len(unterschiede)), key=lambda i: unterschiede[i])
    if unterschiede[schlecht] > 0.1:
        text += L(f" Die meiste Zeit liegt im {SEKTOR_NAMEN.get(schlecht + 1, '')} Sektor.", f" Most of the time is lost in the {SEKTOR_NAMEN.get(schlecht + 1, '')} sector.")
    else:
        text += L(" Da passt alles, weiter so.", " Everything fits there, keep it up.")
    if ziel is None:
        kurve = kurven_satz(stand)
        if kurve:
            text += " " + kurve
    return text


def kurven_analyse(stand):
    """Vergleicht deine letzte Runde mit deiner Bestrunde Kurve für Kurve.
    Gibt die Liste aus acc_telemetrie.vergleichen zurück (größter Verlust zuerst) oder None."""
    aufzeichnung = getattr(stand, "telemetrie", None)
    if aufzeichnung is None:
        return None
    letzte, beste = aufzeichnung.letzte(), aufzeichnung.beste()
    if not letzte or not beste or letzte is beste or not letzte["gueltig"] or letzte["box"]:
        return None
    return acc_telemetrie.vergleichen(letzte, beste, stand.acc.streckenlaenge_m)


def kurven_satz(stand, mindestens=0.15):
    """'In Kurve 5 hast du drei Zehntel verloren, du bremst etwa 12 Meter früher als in deiner Bestrunde.'"""
    ergebnisse = kurven_analyse(stand)
    if not ergebnisse or ergebnisse[0]["verlust"] < mindestens:
        return None
    e = ergebnisse[0]
    grund = acc_telemetrie.grund_text(e)
    text = L(f"Am meisten Zeit verlierst du in Kurve {e['kurve']}, {_kleinzeit(e['verlust'])} auf deine Bestrunde.", f"You lose the most time in turn {e['kurve']}, {_kleinzeit(e['verlust'])} compared to your best lap.")
    return text + (f" {grund[0].upper() + grund[1:]}." if grund else "")


def antwort_rauskommen(stand):
    acc = stand.acc
    if acc.verbindungs_id is None:
        return L("Ich habe gerade keine Verbindung zur Zeitnahme.", "I have no connection to timing right now.")
    verlust = boxenverlust(acc)
    ergebnis = wiedereinstieg(acc, verlust)
    if not ergebnis:
        return L("Ich sehe dein Auto in der Zeitnahme noch nicht.", "I can't see your car in the timing yet.")
    platz, vorne, hinten = ergebnis
    text = (L(f"Ein Boxenstopp kostet hier ungefähr {sekunden_sprechen(verlust)}. "
            f"Wenn du jetzt reinkommst, kommst du ungefähr auf Platz {platz} wieder raus", f"A pit stop costs about {sekunden_sprechen(verlust)} here. "
            f"If you come in now, you will rejoin around P{platz}"))
    if vorne:
        text += L(f", etwa {sekunden_sprechen(max(0.1, vorne[1]))} hinter {name_von(vorne[0], 'dat', mit_platz=False)}{jetzt_auf(vorne[0])}", f", about {sekunden_sprechen(max(0.1, vorne[1]))} behind {name_von(vorne[0], 'dat', mit_platz=False)}{jetzt_auf(vorne[0])}")
    text += "."
    if hinten:
        text += L(f" Hinter dir wäre dann {name_von(hinten[0], mit_platz=False)}{jetzt_auf(hinten[0], ',')} mit etwa {sekunden_sprechen(max(0.1, hinten[1]))} Abstand.", f" Behind you would then be {name_von(hinten[0], mit_platz=False)}{jetzt_auf(hinten[0], ',')} with a gap of about {sekunden_sprechen(max(0.1, hinten[1]))}.")
    return text


def antwort_konstanz(stand):
    protokoll = stand.protokoll
    saubere = protokoll.saubere_runden()
    if len(saubere) < 3:
        return L("Dafür brauche ich noch ein paar saubere Runden von dir, mindestens drei.", "I need a few more clean laps from you for that, at least three.")
    anzahl = min(5, len(saubere))
    spanne, schnitt = protokoll.konstanz(anzahl)
    text = (L(f"Deine letzten {anzahl} sauberen Runden lagen {_kleinzeit(spanne)} auseinander, "
            f"im Schnitt bist du {zeit_sprechen(schnitt)} gefahren.", f"Your last {anzahl} clean laps were within {_kleinzeit(spanne)} of each other, "
            f"your average was {zeit_sprechen(schnitt)}."))
    trend = protokoll.trend(min(6, len(saubere))) if len(saubere) >= 4 else None
    if trend is not None and trend > 0.1:
        text += L(f" Du wirst pro Runde etwa {_kleinzeit(trend)} langsamer, die Reifen bauen ab.", f" You are getting about {_kleinzeit(trend)} slower per lap, the tyres are degrading.")
    elif trend is not None and trend < -0.1:
        text += L(f" Du wirst sogar jede Runde etwa {_kleinzeit(trend)} schneller, sehr gut.", f" You are even getting about {_kleinzeit(trend)} faster every lap, very good.")
    elif spanne < 0.5:
        text += L(" Das ist sehr konstant, weiter so.", " That is very consistent, keep it up.")
    else:
        text += L(" Da geht noch etwas mehr Gleichmäßigkeit.", " There is a bit more consistency to find.")
    return text


def regen_empfehlung(stand):
    """Passen die Reifen zum Wetter? Gibt einen Satz zurück, wenn ein Wechsel sinnvoll ist, sonst None."""
    g = stand.grafik
    if g.session != 2 and g.in_box:
        return None
    regenreifen = "wet" in str(g.reifen_mischung).lower() or bool(g.regenreifen)
    nass = g.grip_status >= 4                    # feucht, nass oder überflutet
    if not regenreifen:
        if nass and g.regen >= 2:
            return (L("Die Strecke wird richtig nass. Mit Slicks verlierst du jetzt viel Zeit, "
                    "komm auf Regenreifen rein.", "The track is getting really wet. You are losing a lot of time on slicks now, "
                    "box for wet tyres."))
        if g.regen_10min >= 3 and g.regen <= 1:
            return (L("In etwa 10 Minuten kommt kräftiger Regen. Plan beim nächsten Stopp "
                    "den Wechsel auf Regenreifen ein.", "Heavy rain is coming in about 10 minutes. Plan the switch to wet tyres "
                    "at your next stop."))
    elif g.regen == 0 and g.regen_10min == 0 and g.grip_status <= 2:
        return (L("Es ist trocken und bleibt auch trocken. Auf Regenreifen bist du jetzt langsamer, "
                "Zeit für Slicks.", "It is dry and it stays dry. You are slower on wet tyres now, "
                "time for slicks."))
    return None


def antwort_reifenwahl(stand):
    empfehlung = regen_empfehlung(stand)
    if empfehlung:
        return empfehlung
    g = stand.grafik
    regenreifen = "wet" in str(g.reifen_mischung).lower() or bool(g.regenreifen)
    if regenreifen:
        return (L("Bleib auf den Regenreifen. Die Strecke ist noch zu nass oder es kommt bald wieder Regen, "
                "für Slicks ist es zu früh.", "Stay on the wets. The track is still too wet or more rain is coming soon, "
                "it's too early for slicks."))
    if g.regen >= 1 or g.regen_10min >= 1:
        return (L("Bleib erst mal auf Slicks. Es ist nur leichter Regen, das lohnt den Wechsel noch nicht. "
                "Ich sag dir Bescheid, wenn es nasser wird.", "Stay on slicks for now. It's only light rain, the switch isn't worth it yet. "
                "I'll let you know when it gets wetter."))
    return L("Bleib auf Slicks, es ist trocken und es kommt auch kein Regen.", "Stay on slicks, it is dry and no rain is coming.")


def antwort_gegner_box(stand):
    acc = stand.acc
    if acc.verbindungs_id is None:
        return L("Ich habe gerade keine Verbindung zur Zeitnahme.", "I have no connection to timing right now.")
    ich = acc.ich()
    liste = acc.rangliste()
    if ich is None or ich not in liste:
        return L("Ich sehe dein Auto in der Zeitnahme noch nicht.", "I can't see your car in the timing yet.")
    mein = liste.index(ich)
    teile = []
    for i in range(max(0, mein - 2), min(len(liste), mein + 3)):
        auto = liste[i]
        if auto is ich:
            continue
        name = gross(L(f"{name_von(auto, mit_platz=False)} auf Platz {i + 1}", f"{name_von(auto, mit_platz=False)} in P{i + 1}"))
        if auto.ort in (2, 3, 4):
            teile.append(L(f"{name} ist gerade in der Box", f"{name} is in the pits right now"))
        elif auto.boxenstopps == 0:
            teile.append(L(f"{name} war noch nicht an der Box", f"{name} hasn't pitted yet"))
        else:
            mal = "einmal" if auto.boxenstopps == 1 else f"{auto.boxenstopps} Mal"
            teile.append(L(f"{name} war schon {mal} an der Box", f"{name} has already pitted {'once' if auto.boxenstopps == 1 else f'{auto.boxenstopps} times'}"))
    if not teile:
        return L("Um dich herum ist gerade niemand.", "There is nobody around you right now.")
    text = ". ".join(gross(t) for t in teile) + "."
    lage = sprit_lage(stand)
    gestoppt_hinter = [a for a in liste[mein + 1:mein + 3] if a.boxenstopps > 0 and a is not ich]
    if lage and lage[1] is not None and lage[2]["stopps"] >= 1 and gestoppt_hinter:
        text += L(" Pass auf den Undercut von hinten auf, dein Stopp steht noch aus.", " Watch out for the undercut from behind, your stop is still to come.")
    return text


def antwort_pole(stand):
    acc = stand.acc
    g = stand.grafik
    if not gueltige_zeit(g.i_beste_zeit):
        return L("Du hast noch keine gültige Runde gefahren.", "You haven't done a valid lap yet.")
    zeiten = [(a.beste_runde, a) for a in acc.autos.values() if gueltige_zeit(a.beste_runde)]
    if not zeiten:
        return L(f"Deine Bestzeit ist {zeit_sprechen(g.i_beste_zeit)}. Die Zeiten der anderen sehe ich gerade nicht.", f"Your best lap is {zeit_sprechen(g.i_beste_zeit)}. I can't see the others' times right now.")
    beste, auto = min(zeiten, key=lambda paar: paar[0])
    if g.i_beste_zeit <= beste or auto is acc.ich():
        return L(f"Du hast die schnellste Zeit von allen, {zeit_sprechen(g.i_beste_zeit)}. Stark!", f"You have the fastest time of all, {zeit_sprechen(g.i_beste_zeit)}. Great!")
    rueckstand = (g.i_beste_zeit - beste) / 1000
    platz = acc.mein_platz() or g.position
    return (L(f"Die Bestzeit hat {name_von(auto)} mit {zeit_sprechen(beste)}. Dir fehlen "
            f"{_kleinzeit(rueckstand)} darauf, damit bist du auf Platz {platz}.", f"The fastest time is held by {name_von(auto)} with {zeit_sprechen(beste)}. You are "
            f"{_kleinzeit(rueckstand)} off, which puts you in P{platz}."))


HILFE_TEXT = L("Du kannst mich nach den Abständen fragen, zum Beispiel zum Vordermann oder zu Platz 3. "
              "Außerdem kann ich dir etwas zum Sprit, zum Boxenstopp, zu den Reifen, den Bremsen, "
              "dem Wetter, Schäden, Strafen, Rundenzeiten und deiner Position sagen. "
              "Frag mich auch, wo du Zeit verlierst, wo du nach dem Stopp rauskommst, wie konstant "
              "du fährst, wer schon an der Box war, ob du Regenreifen brauchst, wie viel Sprit du "
              "für ein Rennen brauchst oder wie du den Reifendruck anpassen sollst. "
              "Sag Lagebericht für einen Überblick, und Funkstille, wenn ich ruhig sein soll.",
               "You can ask me about the gaps, for example to the car ahead or to P3. "
               "I can also tell you about fuel, the pit stop, tyres, brakes, the weather, damage, "
               "penalties, lap times and your position. Ask me where you are losing time, where you "
               "will rejoin after the stop, how consistent you are, who has already pitted, whether "
               "you need wet tyres, how much fuel you need for a race or how to adjust tyre pressures. "
               "Say situation report for an overview, and radio silence if you want me to be quiet.")


ANTWORTEN = {
    "abstand": antwort_abstand, "vergleich": antwort_vergleich,
    "schnellste": antwort_schnellste, "sprit": antwort_sprit, "verbrauch": antwort_verbrauch,
    "spritsparen": antwort_spritsparen, "box": antwort_box, "position": antwort_position,
    "runde": antwort_runde, "rundenzeit": antwort_rundenzeit, "delta": antwort_delta,
    "rest": antwort_rest, "reifendruck": antwort_reifendruck, "reifentemp": antwort_reifentemp,
    "reifenart": antwort_reifenart, "reifen": antwort_reifen, "bremsbelag": antwort_bremsbelag,
    "bremstemp": antwort_bremstemp, "wetter": antwort_wetter, "temperaturen": antwort_temperaturen,
    "grip": antwort_grip, "wind": antwort_wind, "wassertemp": antwort_wassertemp,
    "schaden": antwort_schaden, "elektronik": antwort_elektronik, "stint": antwort_stint,
    "uhrzeit": antwort_uhrzeit, "strafe": antwort_strafe, "flagge": antwort_flagge,
    "gueltig": antwort_gueltig, "pflichtstopp": antwort_pflichtstopp,
    "lagebericht": antwort_lagebericht, "strecke": antwort_strecke,
    "sektoren": antwort_sektoren, "rauskommen": antwort_rauskommen, "konstanz": antwort_konstanz,
    "reifenwahl": antwort_reifenwahl, "gegner_box": antwort_gegner_box, "pole": antwort_pole,
    "box_jetzt": antwort_box_jetzt, "startsprit": antwort_startsprit, "druck_anpassen": antwort_druck_anpassen,
}
MIT_ZUSATZ = {"abstand", "vergleich", "strecke", "sektoren", "startsprit"}


def beantworten(stand, absicht, zusatz):
    """Gibt den Antworttext zurück. Muss mit gehaltener Sperre aufgerufen werden."""
    if absicht == "hilfe":
        return HILFE_TEXT
    if absicht == "danke":
        return random.choice([L("Gerne.", "You're welcome."), "Copy.", L("Kein Problem.", "No problem."), L("Verstanden.", "Understood.")])
    if absicht == "rat":
        if KI_GESTOERT:
            return L("Die KI ist gerade nicht erreichbar. Frag mich gleich nochmal, dann gebe ich dir Rat.", "The AI can't be reached right now. Ask me again in a moment and I'll give you advice.")
        return (L("Für eine Einschätzung brauche ich die KI. Schalte sie in den Einstellungen ein, "
                "dann kann ich dir Rat geben.", "For an assessment I need the AI. Turn it on in the settings, "
                "then I can give you advice."))
    if absicht == "bremsbalance":
        return L("Die Bremsbalance kann ich leider nicht genau auslesen, schau aufs Display.", "I can't read the brake bias exactly, check the display.")
    if not stand.acc_laeuft():
        return L("ACC läuft gerade nicht, oder du bist nicht auf der Strecke.", "ACC is not running right now, or you are not on track.")
    funktion = ANTWORTEN.get(absicht)
    if funktion is None:
        return L("Das habe ich nicht verstanden.", "I didn't understand that.")
    if absicht in MIT_ZUSATZ:
        return funktion(stand, zusatz)
    return funktion(stand)


# ---------------------------------------------------------------------------
# 4) Musik und Lautstärke über die Windows-Medientasten
# ---------------------------------------------------------------------------
MEDIENTASTEN = {
    "musik_pause": (0xB3, 1),     # Play/Pause
    "musik_weiter": (0xB0, 1),    # Nächstes Lied
    "musik_zurueck": (0xB1, 1),   # Vorheriges Lied
    "musik_lauter": (0xAF, 5),    # Lautstärke hoch (5 Stufen)
    "musik_leiser": (0xAE, 5),    # Lautstärke runter
}
MEDIEN_TEXT = L({
    "musik_pause": "Musik: Play/Pause", "musik_weiter": "Musik: nächstes Lied",
    "musik_zurueck": "Musik: Lied zurück", "musik_lauter": "Lautstärke hoch",
    "musik_leiser": "Lautstärke runter",
}, {
    "musik_pause": "Music: play/pause", "musik_weiter": "Music: next song",
    "musik_zurueck": "Music: previous song", "musik_lauter": "Volume up", "musik_leiser": "Volume down",
})


def medien_steuern(absicht):
    import ctypes
    code, anzahl = MEDIENTASTEN[absicht]
    user32 = ctypes.windll.user32
    for _ in range(anzahl):
        user32.keybd_event(code, 0, 0, 0)    # Taste runter
        user32.keybd_event(code, 0, 2, 0)    # Taste hoch


# ---------------------------------------------------------------------------
# 5) Hauptprogramm ohne Fenster (das Fenster ist acc_app.py)
# ---------------------------------------------------------------------------
def main():
    from acc_funktest import Funktaste, aufnehmen, ABTASTRATE
    from acc_stimme import Sprachausgabe
    from faster_whisper import WhisperModel

    os.system("")
    print("=== ACC RENNINGENIEUR ===\n")
    stand = Rennstand()
    stand.starten()

    taste = Funktaste()
    taste.einrichten()
    sprecher = Sprachausgabe(tempo=2, lautstaerke=100, funk=2)

    print("Lade Spracherkennung ...")
    erkennung = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=8)
    print("\nBereit! Taste halten, sprechen, loslassen. (Beenden mit Strg + C)\n")
    sprecher.sagen("Renningenieur ist bereit.")

    try:
        while True:
            if not taste.gedrueckt():
                time.sleep(0.02)
                continue
            sprecher.stoppen()
            audio = aufnehmen(taste)
            if len(audio) / ABTASTRATE < 0.5:
                continue
            abschnitte, _ = erkennung.transcribe(audio, language="de", beam_size=1,
                                                 initial_prompt=WORTHILFE)
            text = " ".join(a.text for a in abschnitte).strip()
            if not text:
                sprecher.sagen("Nicht verstanden.", sofort=True)
                continue
            absicht, zusatz = verstehen(text)
            print(f"Du:        {text}")
            if absicht in MEDIENTASTEN:
                medien_steuern(absicht)
                print(f"Ingenieur: ({MEDIEN_TEXT[absicht]})\n")
                continue
            with stand.sperre:
                antwort = beantworten(stand, absicht, zusatz)
            print(f"Ingenieur: {antwort}\n")
            sprecher.sagen(antwort, sofort=True)
    except KeyboardInterrupt:
        stand.stoppen()
        print("\nBeendet.")


if __name__ == "__main__":
    main()
