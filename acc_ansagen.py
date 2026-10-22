# acc_ansagen.py
# Der Ingenieur meldet sich von selbst, ohne dass du fragen musst:
#   Sprit, Boxenfenster und "Box, Box", Boxenstopp begleiten (Einfahrt, Ausfahrt, wo du rauskommst),
#   Gegner-Stopps und Undercut, Verkehr (Überrunder und Überrundete), Flaggen (Gelb mit Sektor),
#   Strafen, Positionswechsel, Duelle, Bestzeiten, Sektoren, Konstanz und Reifenabbau,
#   Restzeit, Wetter und Regen-Strategie, Schaden, Pitlimiter, Track Limits,
#   Start (Formationsrunde, grünes Licht), Debrief nach dem Rennen und ein Qualifying-Modus.
#
# pruefen() wird zweimal pro Sekunde aufgerufen und gibt neue Meldungen zurück.
# Außerdem schreibt es das Rennprotokoll (stand.protokoll) mit.

import math
import random
import threading
import time

import acc_renningenieur as ri
import acc_gedaechtnis
import acc_telemetrie
import acc_protokoll
from acc_sprache import L, englisch
from acc_abstaende import PHASE_FORMATIONSRUNDE, PHASE_LAEUFT, PHASE_VORBEI, PHASE_VOR_START
from acc_protokoll import boxenverlust, wiedereinstieg
from acc_renningenieur import (REGEN_NAMEN, SCHADEN_ZONEN, abstand_kurz, boxenmenue_hinweis,
                               druck_text, gueltige_zeit, mit_zuspruch, name_von, regen_empfehlung, sekunden_sprechen, sprit_lage,
                               startsprit_text,
                               strafe_text, zahl, zeit_sprechen, jetzt_auf)
from acc_speicher import (FLAGGE_BLAU, FLAGGE_GELB, FLAGGE_GRUEN, FLAGGE_ORANGE,
                          FLAGGE_SCHWARZ, FLAGGE_WEISS, FLAGGE_ZIEL, SESSION_RENNEN, STATUS_LIVE)

# Schlüssel, Beschreibung fürs Fenster, Standard an/aus
ANSAGEN = [
    ("sprit", L("Sprit-Warnungen (noch 3, 2, 1 Runden)", "Fuel warnings (3, 2, 1 laps left)"), True),
    ("box", L('Boxenfenster offen und "Box, Box"', 'Pit window open and "Box, box"'), True),
    ("box_begleitung", L("Boxenstopp begleiten (Einfahrt, Ausfahrt, wo du rauskommst)", "Pit stop guidance (entry, exit, where you rejoin)"), True),
    ("gegner_box", L("Boxenstopps der Gegner und Undercut-Warnungen", "Opponents' pit stops and undercut warnings"), True),
    ("gegner_pace", L("Pace der Gegner: wer langsamer wird oder dir näher kommt", "Opponents' pace: who is slowing down or closing in"), True),
    ("briefing", L("Briefing vor dem Rennen (Startplatz, Sprit, Wetter)", "Pre-race briefing (grid slot, fuel, weather)"), True),
    ("reifendruck", L("Reifendruck-Tipp für den nächsten Stint beim Boxenstopp", "Tyre pressure tip for the next stint at the pit stop"), True),
    ("verkehr", L("Verkehr: Überrunder von hinten, Überrundete vor dir", "Traffic: faster cars lapping you, backmarkers ahead"), True),
    ("renndauer", L("Restzeit (10, 5, 2 Minuten) und letzte Runde", "Time remaining (10, 5, 2 minutes) and last lap"), True),
    ("start_ende", L("Formationsrunde, Start und Debrief nach dem Rennen", "Formation lap, start and debrief after the race"), True),
    ("flaggen", L("Flaggen (Gelb mit Sektor, blau, schwarz, Zielflagge ...)", "Flags (yellow with sector, blue, black, chequered ...)"), True),
    ("strafen", L("Strafen", "Penalties"), True),
    ("positionen", L("Positionswechsel", "Position changes"), True),
    ("duelle", L("Duelle: Vorder- oder Hintermann unter 1 Sekunde", "Battles: car ahead or behind within 1 second"), True),
    ("bestzeit", L("Neue persönliche Bestzeit", "New personal best lap"), True),
    ("sektoren", L("Wo du in einer Runde Zeit verloren hast (Sektoren)", "Where you lost time in a lap (sectors)"), True),
    ("pace", L("Konstanz und Reifenabbau", "Consistency and tyre wear"), True),
    ("quali", L("Qualifying-Modus (Outlap, schnelle Runde, Abstand zur Bestzeit)", "Qualifying mode (out lap, push lap, gap to best time)"), True),
    ("nur_geraden", L("Nicht in Kurven reden: normale Meldungen warten auf die nächste Gerade", "Don't talk in corners: normal messages wait for the next straight"), True),
    ("rundenzeiten", L("Jede Rundenzeit ansagen", "Announce every lap time"), False),
    ("abstaende_runde", L("Abstände nach vorne und hinten jede Runde", "Gaps ahead and behind every lap"), False),
    ("wetter", L("Regen-Vorhersage", "Rain forecast"), True),
    ("regen_strategie", L("Regen-Strategie: wann Regenreifen oder Slicks", "Rain strategy: when to go for wets or slicks"), True),
    ("schaden", L("Schaden und dünne Bremsbeläge", "Damage and thin brake pads"), True),
    ("pitlimiter", L("Pitlimiter vergessen", "Forgot the pit limiter"), True),
    ("tracklimits", L("Ungültige Runde (Track Limits)", "Invalid lap (track limits)"), False),
]
STANDARD_ANSAGEN = {schluessel: an for schluessel, _, an in ANSAGEN}

# Wie gesprächig der Ingenieur ist: 0 ruhig, 1 normal, 2 viel
GESPRAECHIG_STUFEN = [L("Ruhig", "Quiet"), L("Normal", "Normal"), L("Viel", "Chatty")]
# Mindestabstand zwischen zwei "Plauder"-Meldungen in Sekunden, je Stufe
PLAUDER_PAUSE = {0: 400, 1: 240, 2: 45}
# Diese Meldungen sind nur "nice to know" und werden weggelassen, wenn gerade erst etwas gesagt wurde
PLAUDER = {"rundenzeiten", "abstaende_runde", "sektoren", "pace", "tracklimits", "wetter", "gegner_box"}
SEKTOR_WORT = L({1: "ersten", 2: "zweiten", 3: "dritten"}, {1: "first", 2: "second", 3: "third"})


def _zehntel(sekunden):
    """0,3 -> 'drei Zehntel', 0,05 -> 'fünf Hundertstel', 1,2 -> '1,2 Sekunden'."""
    if sekunden >= 1:
        return sekunden_sprechen(sekunden)
    zehntel = round(sekunden * 10)
    if englisch():
        if zehntel >= 10:
            return "one second"
        if zehntel >= 1:
            return "one tenth" if zehntel == 1 else f"{zehntel} tenths"
        return f"{round(sekunden * 100)} hundredths"
    if zehntel >= 1:
        worte = {1: "ein Zehntel", 2: "zwei Zehntel", 3: "drei Zehntel", 4: "vier Zehntel",
                 5: "fünf Zehntel", 6: "sechs Zehntel", 7: "sieben Zehntel", 8: "acht Zehntel",
                 9: "neun Zehntel", 10: "eine Sekunde"}
        return worte[zehntel]
    return f"{round(sekunden * 100)} Hundertstel"


def _reifen_temp(p):
    werte = [t for t in p.reifen_kerntemp if t > 0]
    return sum(werte) / len(werte) if werte else None


class Geradenwaechter:
    """Sagt, ob du gerade auf einer Geraden bist (Vollgas, Lenkrad gerade, nicht bremsen).
    Dann darf der Ingenieur reden, ohne dich in einer Kurve zu stören."""

    def __init__(self, stand):
        self.stand = stand
        self.seit = None
        self.zuletzt = 0.0

    def __call__(self):
        p, g = self.stand.physik, self.stand.grafik
        if p is None or g is None or g.status != STATUS_LIVE:
            return True                      # Menü oder Pause: reden ist kein Problem
        if g.in_boxengasse or g.in_box or p.tempo_kmh < 60:
            return True                      # langsam oder in der Box
        jetzt = time.monotonic()
        if jetzt - self.zuletzt > 0.25:      # länger nicht gefragt: neu anfangen zu zählen
            self.seit = None
        self.zuletzt = jetzt
        gerade = abs(p.lenkwinkel) < 0.06 and p.gas > 0.85 and p.bremse < 0.05
        if not gerade:
            self.seit = None
            return False
        if self.seit is None:
            self.seit = jetzt
        return jetzt - self.seit >= 0.5      # eine halbe Sekunde stabil geradeaus


class Ansagen:
    def __init__(self, schalter=None, fahrer="", gespraechig=1):
        self.gespraechig = gespraechig
        self.letzte_plauderei = -1e9
        self.zuletzt_gesagt = {}             # Schlüssel -> zuletzt benutzte Formulierungen
        self.an = dict(STANDARD_ANSAGEN)
        self.an.update(schalter or {})
        self.fahrer = fahrer
        self.stumm = False          # "Funkstille": nur noch dringende Meldungen
        self.rede_ki = None         # Funktion(fakten) -> Text: die Rede nach der Session von der KI (optional)
        self.nachgereicht = []      # fertige Rede aus dem Hintergrund, wird beim nächsten Durchlauf gesagt
        self.sitzung = None
        self._zuruecksetzen()

    def _zuruecksetzen(self):
        self.runden = None
        self.beste = None
        self.sprit_gewarnt = set()
        self.letzter_tank = None
        self.fenster_gesagt = False
        self.box_gesagt = False
        self.stopp_war_noetig = False
        self.letzte_runde_gesagt = False
        self.zeit = None
        self.flagge = None
        self.strafe = None
        self.gueltig = 1
        self.platz = None
        self.platz_kandidat = None
        self.platz_seit = 0.0
        self.vorne_nah = False
        self.hinten_nah = False
        self.regen_10 = None
        self.regen_30 = None
        self.schaden = None
        self.belag_gesagt = False
        self.in_boxengasse = 0
        self.boxengasse_seit = 0.0
        self.limiter_gesagt = False
        self.abkuehlung = {}
        # neu
        self.phase = None
        self.runde_gueltig_bisher = True     # war die laufende Runde bisher gültig?
        self.box_in_runde = False            # war ich in dieser Runde in der Boxengasse?
        self.sektor_warten = None            # (zeit_ms, bis_wann): auf Sektorzeiten der letzten Runde warten
        self.ausfahrt_faellig = None         # Zeitpunkt für die Meldung nach der Boxenausfahrt
        self.debrief_faellig = None
        self.box_ereignis_zeit = time.monotonic()
        self.gelb_sektoren = [0, 0, 0]
        self.pace_runde = 0                  # wann zuletzt etwas zur Pace gesagt wurde
        self.sektor_runde = 0
        self.outlap = False                  # Quali: gerade auf der Aufwärmrunde
        self.briefing_gesagt = False
        self.aufgegeben = False
        self.in_box_vorher = None
        self.auf_strecke_seit = None
        self.letzter_crash = -1e9
        self.druck_summe = [0.0, 0.0, 0.0, 0.0]
        self.druck_anzahl = 0
        self.gegner_runde = {}               # Auto-Index -> Runde der letzten Pace-Meldung
        self.quali_restrunden = None
        self.bericht_platz = None
        self.bericht_abstaende = {}
        self.feierabend = False              # Session vorbei: nur noch die Rede, danach Ruhe bis zur nächsten Session

    def _frei(self, schluessel, sekunden):
        """Verhindert, dass dieselbe Meldung zu oft kommt."""
        jetzt = time.monotonic()
        if jetzt - self.abkuehlung.get(schluessel, -1e9) < sekunden:
            return False
        self.abkuehlung[schluessel] = jetzt
        return True

    def _anrede(self, wahrscheinlichkeit=0.35):
        """Manchmal mit Namen ansprechen: ', Lutz'."""
        if self.fahrer and random.random() < wahrscheinlichkeit:
            return f", {self.fahrer}"
        return ""

    # -----------------------------------------------------------------------
    def pruefen(self, stand):
        """Gibt eine Liste von (dringend, text) zurück. Mit gehaltener Sperre aufrufen."""
        g, p, s = stand.grafik, stand.physik, stand.statisch
        if g is None or g.status != STATUS_LIVE:
            return []
        protokoll = getattr(stand, "protokoll", None)

        sitzung = (s.strecke, g.session, g.session_index)
        # Springt der Rundenzähler beim grünen Licht auf 0 zurück, ist das kein Neustart der Session
        if (sitzung == self.sitzung and self.runden is not None and g.runden_fertig < self.runden
                and g.session == SESSION_RENNEN and stand.acc.phase == PHASE_LAEUFT and g.runden_fertig == 0):
            self.runden = 0
        if sitzung != self.sitzung or (self.runden is not None and g.runden_fertig < self.runden):
            self.sitzung = sitzung
            self._zuruecksetzen()
            self._startwerte(stand)
            if protokoll is not None:
                protokoll.neu(str(s.strecke), g.session, str(s.auto))
            return []

        meldungen = []

        def sag(art, text, dringend=False):
            if self.an.get(art, False):
                meldungen.append((dringend, text, art))

        rennen = g.session == SESSION_RENNEN
        jetzt = time.monotonic()

        # Fertige Rede aus dem Hintergrund (KI) abholen
        while self.nachgereicht:
            meldungen.append((True, self.nachgereicht.pop(0), "start_ende"))

        # Zielflagge? Dann zuerst die Flagge behandeln, damit die letzte Runde keine Rundenmeldung mehr bekommt
        if not self.feierabend and g.flagge == FLAGGE_ZIEL and self.flagge != FLAGGE_ZIEL:
            self._flaggen(stand, sag, rennen, protokoll)
        if self.feierabend:
            return self._nach_dem_ende(stand, sag, rennen, protokoll, meldungen, jetzt)
        acc = stand.acc

        # Nachgetankt? Dann Sprit-Warnungen neu starten
        if self.letzter_tank is not None and p.tank > self.letzter_tank + 1:
            self.sprit_gewarnt.clear()
            self.fenster_gesagt = self.box_gesagt = False
        self.letzter_tank = p.tank

        # Reifendruck während der Runde mitteln (nur bei Fahrt auf der Strecke, Reifen warm)
        if not g.in_boxengasse and p.tempo_kmh > 60 and all(d > 10 for d in p.reifendruck):
            for i in range(4):
                self.druck_summe[i] += p.reifendruck[i]
            self.druck_anzahl += 1

        # Läuft die Runde noch gültig? War ich in der Box?
        if not g.runde_gueltig:
            self.runde_gueltig_bisher = False
        if g.in_boxengasse:
            self.box_in_runde = True

        # --- Rennphase: Formationsrunde und Start ---
        self._phase(stand, sag, rennen, protokoll)

        # Vor dem Start (Formationsrunde, Aufstellung) und in der ersten Runde ordnet sich das Feld
        # ständig neu. Dann keine Meldungen zu Positionen, Abständen, Verkehr und Gegnern.
        vor_dem_start = rennen and acc.phase in (1, 2, PHASE_VOR_START, PHASE_FORMATIONSRUNDE)
        feld_ruhig = rennen and not vor_dem_start and g.runden_fertig >= 1

        # --- Runde beendet ---
        if g.runden_fertig > self.runden:
            self.runden = g.runden_fertig
            if not vor_dem_start:
                self._runde_beendet(stand, sag, rennen, protokoll)
        elif g.runden_fertig < self.runden and vor_dem_start:
            self.runden = g.runden_fertig          # Zähler springt zum Start zurück
        self._sektoren_nachreichen(stand, sag, protokoll)

        # --- Restzeit ---
        zeit = g.session_rest / 1000
        if self.zeit is not None:
            if rennen:
                for grenze, text in ((600, L("Das Rennen geht noch 10 Minuten.", "The race has 10 minutes to go.")),
                                     (300, L("Das Rennen geht noch 5 Minuten.", "The race has 5 minutes to go.")),
                                     (120, L("Das Rennen geht nur noch 2 Minuten.", "Only 2 minutes of the race to go."))):
                    if self.zeit > grenze >= zeit > 0:
                        sag("renndauer", text)
            if rennen and g.runden_gesamt == 0 and self.zeit > 0 >= zeit:
                text = L("Die Zeit ist abgelaufen.", "Time is up.")
                text += (L(" Nach dieser Runde kommt noch eine weitere.", " After this lap there is one more.") if s.extrarunde
                         else L(f" Das ist jetzt deine letzte Runde{self._anrede(0.6)}!", f" This is your last lap now{self._anrede(0.6)}!"))
                sag("renndauer", text)
        self.zeit = zeit

        # --- Flaggen ---
        self._flaggen(stand, sag, rennen, protokoll)

        # --- Strafen ---
        if g.strafe != self.strafe:
            if g.strafe:
                sag("strafen", strafe_text(g.strafe), True)
                if protokoll is not None:
                    protokoll.strafen += 1
            elif self.strafe:
                sag("strafen", self._v("strafe_weg",
                    L("Deine Strafe ist erledigt.", "Penalty served."),
                    L("Strafe abgesessen, jetzt wieder volle Konzentration.", "Penalty served, full focus again.")))
            self.strafe = g.strafe

        # --- Track Limits ---
        if self.gueltig and not g.runde_gueltig and not g.in_boxengasse and self._frei("tl", 15):
            sag("tracklimits", self._v("tl", L("Diese Runde ist ungültig, Track Limits.", "This lap is invalid, track limits."),
                                       L("Track Limits, die Runde zählt nicht.", "Track limits, the lap doesn't count."),
                                       L("Das war zu weit, Runde ungültig.", "That was too wide, lap invalid.")))
        self.gueltig = g.runde_gueltig

        # --- Zurück in die Box über das Menü (Auto abgestellt, Rennen aufgegeben) ---
        if self._zur_box_teleportiert(stand, sag, rennen, protokoll, vor_dem_start, jetzt):
            return self._auswaehlen(meldungen, jetzt)
        if self.aufgegeben:
            # Fährt er doch wieder los, war es kein Aufgeben
            if not g.in_box and not g.in_boxengasse and p.tempo_kmh > 50:
                self.aufgegeben = False
                sag("box_begleitung", L(f"Okay{self._anrede(0.6)}, du bist wieder unterwegs. Weiter geht's!", f"Okay{self._anrede(0.6)}, you're going again. Let's go!"))
            else:
                return self._auswaehlen([m for m in meldungen if m[2] in ("flaggen", "start_ende")], jetzt)

        # --- Boxengasse: Pitlimiter, Einfahrt, Ausfahrt ---
        self._boxengasse(stand, sag, rennen, protokoll, jetzt)

        # --- Gegner an der Box ---
        if feld_ruhig:
            self._gegner_box(stand, sag)
        else:
            self.box_ereignis_zeit = jetzt         # Boxenfahrten vor dem Start nicht nachträglich melden

        # --- Positionswechsel, Duelle, Verkehr (nur im Rennen, erst ab Runde 2) ---
        if feld_ruhig:
            self._positionen(stand, sag, jetzt)
            self._verkehr(stand, sag)
        else:
            self.platz = self.platz_kandidat = None   # neu anfangen, ohne "Platz verloren" zu melden
            self.vorne_nah = self.hinten_nah = False

        # --- Wetter und Regen-Strategie ---
        self._wetter(stand, sag)

        # --- Schaden ---
        schaden = list(p.schaden)
        if self.schaden is not None:
            neu = [SCHADEN_ZONEN[i] for i in range(5) if schaden[i] > self.schaden[i] + 0.01]
            if neu and self._frei("schaden", 20):
                sag("schaden", L(f"Du hast gerade Schaden {' und '.join(neu[:2])} abbekommen.", f"You just picked up damage at the {' and '.join(neu[:2])}."))
        self.schaden = schaden

        belag = [b for b in p.belag if b > 0]
        if belag and min(belag) < 10 and not self.belag_gesagt:
            self.belag_gesagt = True
            sag("schaden", L(f"Die Bremsbeläge sind fast runter, sie haben nur noch {zahl(min(belag))} Millimeter.", f"The brake pads are almost worn out, only {zahl(min(belag))} millimetres left."))
        elif belag and min(belag) > 20:
            self.belag_gesagt = False    # neue Beläge

        # --- Debrief nach dem Rennen ---
        if self.debrief_faellig and jetzt >= self.debrief_faellig:
            self.debrief_faellig = None
            self._debrief(stand, sag, protokoll)

        return self._auswaehlen(meldungen, jetzt)

    def _nach_dem_ende(self, stand, sag, rennen, protokoll, meldungen, jetzt):
        """Nach der Zielflagge: Runden still mitschreiben, dann die Rede halten, danach Ruhe.
        Keine Meldungen mehr zu Positionen, Flaggen, Box oder dem Zurückkehren über das Menü."""
        g = stand.grafik
        still = lambda *argumente, **schluessel: None
        if self.runden is not None and g.runden_fertig > self.runden:
            self.runden = g.runden_fertig
            self._runde_beendet(stand, still, rennen, protokoll)
        self._sektoren_nachreichen(stand, still, protokoll)
        # Zustände nachführen, damit nach der nächsten Session nichts Altes gemeldet wird
        self.flagge, self.phase = g.flagge, stand.acc.phase
        self.in_box_vorher = bool(g.in_box)
        self.in_boxengasse = g.in_boxengasse
        self.gelb_sektoren = [g.gelb_sektor_1, g.gelb_sektor_2, g.gelb_sektor_3]
        self.strafe, self.gueltig = g.strafe, g.runde_gueltig
        self.zeit = g.session_rest / 1000
        if self.debrief_faellig and jetzt >= self.debrief_faellig:
            self.debrief_faellig = None
            self._debrief(stand, sag, protokoll)
        # Nur Zielflagge und Rede durchlassen (auch bei Funkstille)
        return [(True, t) for d, t, art in meldungen if art in ("start_ende", "flaggen")]

    def _auswaehlen(self, meldungen, jetzt):
        """Nicht zutexten: Dringendes kommt immer. Wichtiges kommt, aber gebündelt in EINEM
        Funkspruch. Plaudereien (Rundenzeit, Abstände, Sektoren ...) nur, wenn eine Weile
        nichts gesagt wurde, und dann höchstens eine."""
        if self.stumm:
            return [(d, t) for d, t, _ in meldungen if d]
        dringend = [(True, t) for d, t, _ in meldungen if d]
        wichtig = [t for d, t, art in meldungen if not d and art not in PLAUDER]
        plauder = [t for d, t, art in meldungen if not d and art in PLAUDER]
        pause = PLAUDER_PAUSE.get(self.gespraechig, 60)
        if plauder and jetzt - self.letzte_plauderei >= pause and len(wichtig) <= 1:
            wichtig.append(plauder[0])
            self.letzte_plauderei = jetzt
        elif wichtig:
            self.letzte_plauderei = max(self.letzte_plauderei, jetzt - pause / 2)   # auch Wichtiges zählt
        ergebnis = dringend
        if wichtig:
            ergebnis.append((False, " ".join(wichtig)))
        return ergebnis

    def _v(self, schluessel, *varianten):
        """Sucht eine Formulierung aus, die zuletzt nicht benutzt wurde, damit es nicht eintönig wird."""
        varianten = [v for v in varianten if v]
        zuletzt = self.zuletzt_gesagt.setdefault(schluessel, [])
        frisch = [v for v in range(len(varianten)) if v not in zuletzt] or list(range(len(varianten)))
        wahl = random.choice(frisch)
        zuletzt.append(wahl)
        del zuletzt[:-max(1, len(varianten) // 2)]
        return varianten[wahl]

    # -----------------------------------------------------------------------
    def _startwerte(self, stand):
        """Beim Start einer Session: alles merken, damit nichts sofort losplappert."""
        g, p = stand.grafik, stand.physik
        self.runden = g.runden_fertig
        self.beste = g.i_beste_zeit
        self.letzter_tank = p.tank
        self.zeit = g.session_rest / 1000
        self.flagge = g.flagge
        self.strafe = g.strafe
        self.gueltig = g.runde_gueltig
        self.regen_10, self.regen_30 = g.regen_10min, g.regen_30min
        self.schaden = list(p.schaden)
        self.in_boxengasse = g.in_boxengasse
        self.phase = stand.acc.phase
        self.gelb_sektoren = [g.gelb_sektor_1, g.gelb_sektor_2, g.gelb_sektor_3]
        self.box_ereignis_zeit = time.monotonic()

    # --- Start und Ende -----------------------------------------------------
    def _phase(self, stand, sag, rennen, protokoll):
        phase = stand.acc.phase
        if phase == self.phase:
            return
        alt, self.phase = self.phase, phase
        if not rennen or alt is None:
            return
        name = f", {self.fahrer}" if self.fahrer else ""
        if phase in (PHASE_VOR_START, PHASE_FORMATIONSRUNDE) and not self.briefing_gesagt:
            self.briefing_gesagt = True
            sag("briefing", self._briefing(stand))
        if phase == PHASE_FORMATIONSRUNDE:
            sag("start_ende", L(f"Formationsrunde{name}. Bring Reifen und Bremsen auf Temperatur, "
                              f"aber halt genug Abstand zu den anderen.", f"Formation lap{name}. Get the tyres and brakes up to temperature, "
                              f"but keep enough distance to the others."))
        elif phase == PHASE_LAEUFT and alt < PHASE_LAEUFT:
            platz = stand.acc.mein_platz() or stand.grafik.position
            if protokoll is not None and platz:
                protokoll.startplatz = platz
            sag("start_ende", self._v("start",
                L(f"Grünes Licht, los geht's! Viel Glück{name}, und pass in der ersten Kurve auf.", f"Lights out, go go go! Good luck{name}, and watch turn one."),
                L(f"Und los{name}! Sauber durch die erste Kurve, das Rennen ist lang.", f"Go{name}! Clean through turn one, it's a long race."),
                L(f"Grün! Gib Gas{name}, aber keine Risiken in Kurve eins.", f"Green! Go{name}, but no risks into turn one.")),
                True)
        elif phase >= PHASE_VORBEI and alt < PHASE_VORBEI and not self.aufgegeben:
            self.feierabend = True
            if self.debrief_faellig is None and protokoll is not None and not protokoll.ende_gemeldet:
                self.debrief_faellig = time.monotonic() + 3

    def _zur_box_teleportiert(self, stand, sag, rennen, protokoll, vor_dem_start, jetzt):
        """Erkennt, wenn du über das Menü direkt in die Box zurückkehrst (ohne durch die Boxengasse zu
        fahren). Im Rennen heißt das: Auto abgestellt, das Rennen ist vorbei."""
        g, p = stand.grafik, stand.physik
        # Unfall merken: plötzlich viel Schaden
        if self.schaden is not None and sum(p.schaden) > sum(self.schaden) + 0.05:
            self.letzter_crash = jetzt
        vorher_draussen = self.in_box_vorher is False and not self.in_boxengasse
        self.in_box_vorher = bool(g.in_box)
        if not (g.in_box and vorher_draussen) or not rennen or vor_dem_start or self.aufgegeben:
            return False
        if g.flagge == FLAGGE_ZIEL or stand.acc.phase >= PHASE_VORBEI or (protokoll is not None and protokoll.ende_gemeldet):
            self.feierabend = True                    # Rennen war schon zu Ende: kein "Aufgeben"
            if protokoll is not None and not protokoll.ende_gemeldet and self.debrief_faellig is None:
                self.debrief_faellig = jetzt + 2
            return False
        self.aufgegeben = True
        self.in_boxengasse = g.in_boxengasse          # keine "Willkommen in der Boxengasse"-Meldung
        name = self.fahrer
        teile = [L(f"Okay{', ' + name if name else ''}, du bist zurück in der Box. Damit ist das Rennen für uns leider vorbei.", f"Okay{', ' + name if name else ''}, you're back in the pits. That's the end of the race for us, unfortunately.")]
        if jetzt - self.letzter_crash < 120:
            teile.append(L("Nach dem Unfall war mit dem Auto nicht mehr viel zu machen.", "After the crash there wasn't much more we could do with the car."))
        platz = self.platz or stand.acc.mein_platz()
        if protokoll is not None and protokoll.runden:
            text = L(f"Bis dahin bist du {len(protokoll.runden)} {'Runde' if len(protokoll.runden) == 1 else 'Runden'} gefahren", f"Up to then you did {len(protokoll.runden)} {'lap' if len(protokoll.runden) == 1 else 'laps'}")
            if platz:
                text += L(f" und lagst auf Platz {platz}", f" and were in P{platz}")
            beste = protokoll.bestzeit()
            if beste:
                text += L(f". Deine schnellste Runde war {zeit_sprechen(beste)}", f". Your fastest lap was {zeit_sprechen(beste)}")
            teile.append(text + ".")
        teile.append(self._v("aufgegeben",
            L("Kopf hoch, das passiert den Besten. Beim nächsten Rennen holen wir uns das zurück.", "Heads up, it happens to the best. We'll get it back in the next race."),
            L("Schade, aber daraus lernen wir. Im nächsten Rennen greifen wir wieder an.", "A shame, but we learn from it. Next race we attack again."),
            L("Das ist bitter, aber abhaken. Die Pace war da, das nächste Rennen wird besser.", "That one hurts, but let it go. The pace was there, the next race will be better.")))
        sag("start_ende", " ".join(teile), True)
        if protokoll is not None and not protokoll.ende_gemeldet:
            protokoll.ende_gemeldet = True
            protokoll.aufgegeben = True
            protokoll.endplatz = None
            try:
                protokoll.telemetrie = stand.telemetrie.export(stand.acc.streckenlaenge_m)
                protokoll.karte = acc_protokoll.karte_von(stand.acc)
                protokoll.speichern()
            except Exception:
                pass
        return True

    def _briefing(self, stand):
        """Kurzer Überblick vor dem Start: Startplatz, Renndauer, Sprit, Wetter, Nachbarn."""
        g, s, acc = stand.grafik, stand.statisch, stand.acc
        strecke = str(s.strecke).replace("_", " ").title()
        teile = [L(f"Willkommen zum Rennen in {strecke}{self._anrede(1.0)}.", f"Welcome to the race at {strecke}{self._anrede(1.0)}.")]
        platz = acc.mein_platz() or g.position
        gesamt = len(acc.rangliste())
        if platz:
            teile.append(L(f"Du startest von Platz {platz}", f"You start from P{platz}") + (L(f" von {gesamt}.", f" of {gesamt}.") if gesamt else "."))
            vorne = acc.auto_auf_platz(platz - 1) if platz > 1 else None
            if vorne is not None:
                teile.append(L(f"Vor dir steht {name_von(vorne)}.", f"Ahead of you is {name_von(vorne)}."))
        if g.runden_gesamt > 0:
            teile.append(L(f"Das Rennen geht über {g.runden_gesamt} Runden.", f"The race is {g.runden_gesamt} laps long."))
        elif g.session_rest > 0:
            teile.append(L(f"Das Rennen geht {round(g.session_rest / 60000)} Minuten.", f"The race is {round(g.session_rest / 60000)} minutes long."))
        if ri.startsprit_berechnen(stand)[0] is not None:
            teile.append(startsprit_text(stand, mit_tank=True, im_briefing=True))
        if g.regen > 0:
            teile.append(L(f"Es gibt gerade {REGEN_NAMEN[min(g.regen, 5)]}.", f"Right now there is {REGEN_NAMEN[min(g.regen, 5)]}."))
        elif g.regen_30min > 0 or g.regen_10min > 0:
            teile.append(L(f"Achtung, später ist {REGEN_NAMEN[min(max(g.regen_10min, g.regen_30min), 5)]} angesagt.", f"Heads up, {REGEN_NAMEN[min(max(g.regen_10min, g.regen_30min), 5)]} is forecast later."))
        else:
            teile.append(L("Es bleibt trocken.", "It stays dry."))
        teile.append(L("Viel Erfolg, wir schaffen das zusammen.", "Good luck, we'll do this together."))
        return " ".join(teile)

    def _gegner_pace(self, stand, sag):
        """Wird ein Gegner in deiner Nähe langsamer, oder kommt einer schnell näher?"""
        acc = stand.acc
        ich = acc.ich()
        liste = acc.rangliste()
        if ich is None or ich not in liste or self.runden is None:
            return
        mein_platz = liste.index(ich) + 1

        def saubere(auto, anzahl):
            runden = [r for r in auto.runden_historie if r["gueltig"] and not r["box"]]
            return runden[-anzahl:], runden

        meine, _ = saubere(ich, 3)
        mein_schnitt = sum(r["zeit"] for r in meine) / len(meine) if len(meine) == 3 else None
        for richtung in (-1, 1, -2):
            nr = mein_platz + richtung
            if nr < 1 or nr > len(liste):
                continue
            auto = liste[nr - 1]
            if self.runden - self.gegner_runde.get(auto.index, -99) < 6:
                continue
            letzte, alle = saubere(auto, 3)
            if len(letzte) < 3 or len(alle) < 5:
                continue
            beste = min(r["zeit"] for r in alle)
            schnitt = sum(r["zeit"] for r in letzte) / 3
            zeiten = [r["zeit"] for r in letzte]
            name = name_von(auto)
            Name, name_dat, name_akk = gross_satz(name), name_von(auto, "dat"), name_von(auto, "akk")
            langsamer = (schnitt - beste) / 1000
            if langsamer > 0.8 and zeiten[0] <= zeiten[1] <= zeiten[2]:
                self.gegner_runde[auto.index] = self.runden
                if richtung < 0:
                    sag("gegner_pace", self._v("gp_vorne_ab",
                        L(f"{Name} vor dir wird langsamer, seine letzten Runden waren {sekunden_sprechen(langsamer)} "
                        f"über seiner Bestzeit. Die Reifen bauen ab, das ist deine Chance.", f"{Name} ahead of you is slowing down, his last laps were {sekunden_sprechen(langsamer)} "
                        f"off his best. The tyres are going off, this is your chance."),
                        L(f"Vorne lässt {name} nach, gut {sekunden_sprechen(langsamer)} pro Runde. Bleib dran, er wird angreifbar.", f"Up ahead {name} is fading, a good {sekunden_sprechen(langsamer)} per lap. Stay on him, he's getting vulnerable.")))
                else:
                    sag("gegner_pace", self._v("gp_hinten_ab",
                        L(f"{Name} hinter dir verliert gerade Zeit, er ist {sekunden_sprechen(langsamer)} langsamer als am Anfang. "
                        f"Du kannst etwas durchatmen.", f"{Name} behind you is losing time, he is {sekunden_sprechen(langsamer)} slower than at the start. "
                        f"You can breathe a little."),
                        L(f"Hinten wird {name} langsamer. Halt dein Tempo, dann bist du ihn bald los.", f"{Name} behind is slowing down. Keep your pace and you'll be rid of him soon.")))
            elif mein_schnitt and richtung == 1:
                schneller = (mein_schnitt - schnitt) / 1000
                if schneller > 0.4:
                    self.gegner_runde[auto.index] = self.runden
                    sag("gegner_pace", self._v("gp_hinten_schnell",
                        L(f"Achtung, {name} hinter dir ist im Moment {sekunden_sprechen(schneller)} pro Runde schneller als du.", f"Heads up, {name} behind you is currently {sekunden_sprechen(schneller)} per lap faster than you."),
                        L(f"{Name} kommt mit Tempo, gut {sekunden_sprechen(schneller)} pro Runde schneller. Mach dich breit, wenn er kommt.", f"{Name} is coming with pace, a good {sekunden_sprechen(schneller)} per lap faster. Make yourself wide when he comes.")))

    def _debrief(self, stand, sag, protokoll):
        if protokoll is None or protokoll.ende_gemeldet:
            return
        protokoll.ende_gemeldet = True
        acc, g = stand.acc, stand.grafik
        protokoll.endplatz = protokoll.endplatz or acc.mein_platz() or g.position or None
        rueckstand = None
        if g.session != SESSION_RENNEN:
            zeiten = [a.beste_runde for a in acc.autos.values() if gueltige_zeit(a.beste_runde)]
            meine = protokoll.bestzeit()
            if zeiten and meine:
                rueckstand = max(0.0, (meine - min(zeiten)) / 1000) or None
        ersatz = protokoll.debrief(self.fahrer, rueckstand)
        if self.rede_ki is not None and self.an.get("start_ende", False):
            fakten = protokoll.fakten_text(rueckstand, self.fahrer)

            def im_hintergrund():
                try:
                    text = self.rede_ki(fakten) or ersatz
                except Exception:
                    text = ersatz
                self.nachgereicht.append(text)
            threading.Thread(target=im_hintergrund, daemon=True).start()
        else:
            sag("start_ende", ersatz, True)
        try:
            protokoll.telemetrie = stand.telemetrie.export(stand.acc.streckenlaenge_m)
            protokoll.karte = acc_protokoll.karte_von(stand.acc)
            protokoll.speichern()
        except OSError:
            pass

    # --- Flaggen --------------------------------------------------------------
    def _flaggen(self, stand, sag, rennen, protokoll):
        g = stand.grafik
        # Gelb in einem bestimmten Sektor
        gelb = [g.gelb_sektor_1, g.gelb_sektor_2, g.gelb_sektor_3]
        for nummer, (vorher, jetzt) in enumerate(zip(self.gelb_sektoren, gelb), start=1):
            if jetzt and not vorher and self._frei(f"gelb{nummer}", 15):
                mein_sektor = g.sektor + 1
                text = L(f"Gelbe Flagge im {SEKTOR_WORT[nummer]} Sektor!", f"Yellow flag in the {SEKTOR_WORT[nummer]} sector!")
                if nummer == mein_sektor:
                    text += L(" Das ist genau in deinem Abschnitt, vorsichtig und nicht überholen.", " That is right in your section, careful and no overtaking.")
                    sag("flaggen", text, True)
                elif nummer == mein_sektor % 3 + 1:
                    text += L(" Das kommt gleich vor dir, sei vorsichtig.", " That is coming up ahead of you, be careful.")
                    sag("flaggen", text, True)
                else:
                    sag("flaggen", text)
                self.abkuehlung["gelb"] = time.monotonic()      # allgemeine Gelb-Meldung nicht doppelt
        self.gelb_sektoren = gelb

        if g.flagge == self.flagge:
            return
        alt, self.flagge = self.flagge, g.flagge
        f = g.flagge
        if f == FLAGGE_GELB and self._frei("gelb", 10):
            sag("flaggen", self._v("f_gelb",
                L("Gelbe Flagge! Bitte vorsichtig fahren und nicht überholen.", "Yellow flag! Careful, no overtaking."),
                L("Gelb! Vom Gas, nicht überholen.", "Yellow! Lift, no overtaking."),
                L("Achtung, gelbe Flagge. Halt die Position und sei bereit zu bremsen.", "Heads up, yellow flag. Hold position and be ready to brake.")), True)
        elif f == FLAGGE_BLAU and self._frei("blau", 30):
            sag("flaggen", self._v("f_blau",
                L("Blaue Flagge! Ein schnelleres Auto ist hinter dir, bitte lass es vorbei.", "Blue flag! Faster car behind, let it through."),
                L("Blau! Lass ihn auf der nächsten Geraden vorbei, keine Zeit verlieren.", "Blue! Let him by on the next straight, don't lose time."),
                L("Blaue Flagge für dich. Bleib auf deiner Linie, er geht vorbei.", "Blue flag for you. Hold your line, he'll go past.")), True)
        elif f == FLAGGE_SCHWARZ:
            sag("flaggen", L("Schwarze Flagge! Du wirst aus dem Rennen genommen.", "Black flag! You are being taken out of the race."), True)
        elif f == FLAGGE_WEISS and self._frei("weiss", 20):
            sag("flaggen", L("Weiße Flagge. Vor dir ist ein langsames Auto auf der Strecke.", "White flag. There is a slow car on track ahead of you."))
        elif f == FLAGGE_ORANGE and self._frei("orange", 30):
            sag("flaggen", L("Orange Flagge! Das Auto ist beschädigt, komm bitte an die Box.", "Meatball flag! The car is damaged, box please."), True)
        elif f == FLAGGE_ZIEL and self._frei("ziel", 60):
            platz = stand.acc.mein_platz() or g.position
            if self.aufgegeben:
                sag("flaggen", L("Die Zielflagge ist gefallen, das Rennen ist jetzt offiziell vorbei.", "The chequered flag is out, the race is now officially over."))
                return
            if rennen:
                sag("flaggen", self._v("f_ziel",
                    L(f"Zielflagge! Du bringst ihn auf Platz {platz} nach Hause.", f"Chequered flag! You bring it home in P{platz}."),
                    L(f"Und das ist die Zielflagge. Platz {platz}, gut gefahren.", f"And that's the flag. P{platz}, well driven."),
                    L(f"Zielflagge, Platz {platz}. Danke für das Rennen, Cooldown-Runde.", f"Chequered flag, P{platz}. Thanks for the race, cool-down lap.")), True)
            else:
                sag("flaggen", L("Zielflagge, die Session ist vorbei.", "Chequered flag, the session is over."))
            self.feierabend = True
            if protokoll is not None and not protokoll.ende_gemeldet and self.debrief_faellig is None:
                protokoll.endplatz = platz
                self.debrief_faellig = time.monotonic() + 4
        elif f == FLAGGE_GRUEN and alt == FLAGGE_GELB and self._frei("gruen", 10):
            sag("flaggen", self._v("f_gruen",
                L("Grüne Flagge, die Strecke ist wieder frei.", "Green flag, the track is clear again."),
                L("Grün, grün, grün. Wieder Vollgas.", "Green, green, green. Back to racing."),
                L("Gelb ist aufgehoben, grüne Flagge.", "Yellow is cleared, green flag.")))

    # --- Runde beendet ----------------------------------------------------------
    def _runde_beendet(self, stand, sag, rennen, protokoll):
        g, p = stand.grafik, stand.physik
        acc = stand.acc
        platz = acc.mein_platz() or g.position or None
        war_outlap = self.box_in_runde

        # Schneller als die bisherige Bestzeit, aber ACC übernimmt sie nicht als Bestzeit? Dann war die Runde ungültig.
        if (gueltige_zeit(self.beste) and gueltige_zeit(g.i_letzte_zeit) and g.i_letzte_zeit < self.beste - 5
                and g.i_beste_zeit == self.beste):
            self.runde_gueltig_bisher = False
        if not self.runde_gueltig_bisher and gueltige_zeit(g.i_letzte_zeit):
            try:
                stand.telemetrie.ungueltig_markieren(g.i_letzte_zeit)
            except AttributeError:
                pass
        # Ins Protokoll schreiben (Sektorzeiten kommen über die Zeitnahme etwas später)
        if protokoll is not None and gueltige_zeit(g.i_letzte_zeit):
            protokoll.runde_eintragen(g.runden_fertig, g.i_letzte_zeit, self.runde_gueltig_bisher,
                                      self.box_in_runde, platz, p.tank, [])
            self.sektor_warten = (g.i_letzte_zeit, time.monotonic() + 4)
            if protokoll.runden and self.druck_anzahl >= 20:
                protokoll.runden[-1]["druck"] = [round(x / self.druck_anzahl, 2) for x in self.druck_summe]
        self.druck_summe, self.druck_anzahl = [0.0, 0.0, 0.0, 0.0], 0
        # Verbrauch und Rundenzeit für diese Strecke merken (für den Startsprit beim nächsten Mal)
        if (self.runde_gueltig_bisher and not self.box_in_runde and gueltige_zeit(g.i_letzte_zeit)
                and gueltige_zeit(g.i_beste_zeit) and g.i_letzte_zeit < g.i_beste_zeit + 3000):
            try:
                acc_gedaechtnis.runde_merken(str(stand.statisch.strecke), str(stand.statisch.auto),
                                             stand.messer.verbrauch_schnitt(), g.i_letzte_zeit / 1000)
            except Exception:
                pass
        gueltig = self.runde_gueltig_bisher
        self.runde_gueltig_bisher = True
        self.box_in_runde = bool(g.in_boxengasse)

        # Rundenzeit und Bestzeit
        neue_bestzeit = (gueltige_zeit(g.i_beste_zeit) and g.i_beste_zeit != self.beste
                         and g.i_beste_zeit == g.i_letzte_zeit and gueltige_zeit(self.beste))
        if neue_bestzeit or (gueltige_zeit(g.i_beste_zeit) and not gueltige_zeit(self.beste)):
            try:
                acc_gedaechtnis.bestzeit_merken(str(stand.statisch.strecke), str(stand.statisch.auto),
                                                g.i_beste_zeit, {0: "Training", 1: "Qualifying", 2: "Rennen"}.get(g.session, "Session"))
            except Exception:
                pass
        if not rennen and self.an.get("quali"):
            self._quali_runde(stand, sag, neue_bestzeit, gueltig, war_outlap)
        elif neue_bestzeit:
            zeit = zeit_sprechen(g.i_beste_zeit)
            sag("bestzeit", self._v("bestzeit",
                L(f"Neue persönliche Bestzeit{self._anrede()}! {zeit}.", f"New personal best{self._anrede()}! {zeit}."),
                L(f"Lila Runde{self._anrede()}! {zeit}, so schnell warst du heute noch nie.", f"Purple lap{self._anrede()}! {zeit}, you haven't been this fast all day."),
                L(f"Das war deine schnellste Runde bisher, {zeit}. Stark!", f"That was your fastest lap so far, {zeit}. Great!"),
                L(f"Bestzeit! {zeit}. Genau so weiter{self._anrede()}.", f"Best lap! {zeit}. Keep it like that{self._anrede()}.")))
        elif gueltige_zeit(g.i_letzte_zeit) and rennen is False and self._rundenzeit_satz(g):
            sag("rundenzeiten", self._rundenzeit_satz(g))
        self.beste = g.i_beste_zeit

        if rennen:
            # Erste Runde geschafft
            if g.runden_fertig == 1 and protokoll is not None and protokoll.startplatz and platz:
                differenz = protokoll.startplatz - platz
                text = L(f"Die erste Runde ist geschafft, du liegst auf Platz {platz}.", f"First lap done, you are in P{platz}.")
                if differenz > 0:
                    text += L(f" Du hast schon {'einen Platz' if differenz == 1 else f'{differenz} Plätze'} gutgemacht, stark!", f" You've already gained {'one place' if differenz == 1 else f'{differenz} places'}, great!")
                elif differenz < 0:
                    text += L(" Ein paar Plätze verloren, aber das Rennen ist noch lang. Ruhig bleiben.", " Lost a few places, but the race is still long. Stay calm.")
                sag("start_ende", text)

            # Rundenbericht: Rundenzeit und was sich bei den Abständen getan hat, in einem Satz
            bericht = self._rundenbericht(stand, g, platz, neue_bestzeit, gueltig)
            if bericht:
                sag("abstaende_runde" if self.an.get("abstaende_runde") else "rundenzeiten", bericht)

            # Konstanz und Reifenabbau
            self._pace(stand, sag, protokoll)
            self._gegner_pace(stand, sag)

        # Letzte Runde bei Rennen über Runden
        if (rennen and g.runden_gesamt > 0 and g.runden_fertig == g.runden_gesamt - 1
                and not self.letzte_runde_gesagt):
            self.letzte_runde_gesagt = True
            sag("renndauer", self._v("letzte",
                L(f"Das ist jetzt die letzte Runde{self._anrede(0.6)}!", f"This is the last lap{self._anrede(0.6)}!"),
                L(f"Letzte Runde{self._anrede(0.6)}. Bring ihn sauber nach Hause.", f"Final lap{self._anrede(0.6)}. Bring it home clean."),
                L(f"Weiße Fahne, letzte Runde{self._anrede(0.6)}. Alles geben, aber keine Fehler.", f"Last lap{self._anrede(0.6)}. Give it everything, but no mistakes.")))

        # Sprit und Box
        self._sprit_und_box(stand, sag, rennen)

    def _rundenzeit_satz(self, g):
        zeit = zeit_sprechen(g.i_letzte_zeit)
        delta = (g.i_letzte_zeit - g.i_beste_zeit) / 1000 if gueltige_zeit(g.i_beste_zeit) else None
        if delta is not None and 0 < delta < 0.3:
            return self._v("rz_nah", L(f"{zeit}, ganz knapp an deiner Bestzeit.", f"{zeit}, very close to your best."),
                           L(f"Gute Runde, {zeit}. Nur {_zehntel(delta)} über deiner Bestzeit.", f"Good lap, {zeit}. Only {_zehntel(delta)} off your best."),
                           L(f"{zeit}. Das passt, nah an der Bestzeit.", f"{zeit}. That's fine, close to your best."))
        if delta is not None and delta > 1.5:
            return self._v("rz_langsam", L(f"{zeit}, das war {sekunden_sprechen(delta)} über deiner Bestzeit.", f"{zeit}, that was {sekunden_sprechen(delta)} off your best."),
                           L(f"Die Runde war etwas langsamer, {zeit}.", f"That lap was a bit slower, {zeit}."),
                           L(f"{zeit}. Da ging Zeit verloren, Kopf hoch, nächste Runde.", f"{zeit}. Some time lost there, heads up, next lap."))
        if self.gespraechig < 2:
            return ""                         # eine ganz normale Runde ist keine Meldung wert
        return self._v("rz", L(f"Letzte Runde {zeit}.", f"Last lap {zeit}."), L(f"{zeit} in der letzten Runde.", f"{zeit} on the last lap."),
                       L(f"Runde {g.runden_fertig}: {zeit}.", f"Lap {g.runden_fertig}: {zeit}."), L(f"Du bist {zeit} gefahren.", f"You did a {zeit}."))

    def _rundenbericht(self, stand, g, platz, neue_bestzeit, gueltig):
        """Ein kurzer, abwechslungsreicher Bericht. Abstände nur, wenn sich etwas getan hat."""
        acc = stand.acc
        teile = []
        if self.an.get("rundenzeiten") and gueltige_zeit(g.i_letzte_zeit) and not neue_bestzeit and gueltig:
            satz = self._rundenzeit_satz(g)
            if satz:
                teile.append(satz)
        if self.an.get("abstaende_runde") and platz:
            if platz != self.bericht_platz and self.bericht_platz is not None:
                teile.append(self._v("b_platz", L(f"Du bist jetzt auf Platz {platz}.", f"You are now in P{platz}."), L(f"Platz {platz} jetzt.", f"P{platz} now.")))
            self.bericht_platz = platz
            for richtung, auto in (("vorne", acc.auto_auf_platz(platz - 1) if platz > 1 else None),
                                   ("hinten", acc.auto_auf_platz(platz + 1))):
                if auto is None:
                    continue
                art, wert = acc.abstand_zu(auto)
                if art != "sek" or wert is None:
                    continue
                wert = abs(wert)
                schluessel = (richtung, auto.index)
                alt = self.bericht_abstaende.get(schluessel)
                self.bericht_abstaende[schluessel] = wert
                name = name_von(auto)
                Name, name_dat, name_akk = gross_satz(name), name_von(auto, "dat"), name_von(auto, "akk")
                if alt is None:
                    if richtung == "vorne":
                        teile.append(self._v("b_neu_v", L(f"Vor dir ist {name}, {sekunden_sprechen(wert)}.", f"Ahead of you is {name}, {sekunden_sprechen(wert)}."),
                                             L(f"Auf {name_akk} vor dir fehlen {sekunden_sprechen(wert)}.", f"{sekunden_sprechen(wert)} to {name_akk} ahead of you.")))
                    else:
                        teile.append(self._v("b_neu_h", L(f"Hinter dir ist {name}, {sekunden_sprechen(wert)}.", f"Behind you is {name}, {sekunden_sprechen(wert)}."),
                                             L(f"{Name} ist {sekunden_sprechen(wert)} hinter dir.", f"{Name} is {sekunden_sprechen(wert)} behind you.")))
                    continue
                aenderung = wert - alt
                if abs(aenderung) < 0.4:
                    continue                                # nichts Neues, nicht erwähnen
                menge = _zehntel(abs(aenderung))
                if richtung == "vorne" and aenderung < 0:
                    teile.append(self._v("b_v_auf",
                        L(f"Auf {name_akk} hast du {menge} gutgemacht, noch {sekunden_sprechen(wert)}.", f"You gained {menge} on {name_akk}, still {sekunden_sprechen(wert)}."),
                        L(f"Du holst auf {name_akk} auf, {menge} in einer Runde. Jetzt {sekunden_sprechen(wert)}.", f"You're catching {name_akk}, {menge} in one lap. Now {sekunden_sprechen(wert)}."),
                        L(f"{gross_satz(menge)} schneller als {name}, der Abstand ist jetzt {sekunden_sprechen(wert)}.", f"{gross_satz(menge)} faster than {name}, the gap is now {sekunden_sprechen(wert)}.")))
                elif richtung == "vorne":
                    teile.append(self._v("b_v_ab",
                        L(f"{Name} ist {menge} weggefahren, jetzt {sekunden_sprechen(wert)} vor dir.", f"{Name} pulled away by {menge}, now {sekunden_sprechen(wert)} ahead of you."),
                        L(f"Der Abstand zu {name_dat} wächst, {sekunden_sprechen(wert)}.", f"The gap to {name_dat} is growing, {sekunden_sprechen(wert)}.")))
                elif aenderung < 0:
                    teile.append(self._v("b_h_auf",
                        L(f"{Name} kommt näher, {menge} in einer Runde. Noch {sekunden_sprechen(wert)}.", f"{Name} is closing in, {menge} in one lap. Still {sekunden_sprechen(wert)}."),
                        L(f"Hinten macht {name} Druck, nur noch {sekunden_sprechen(wert)}.", f"{Name} behind is pushing, only {sekunden_sprechen(wert)} now.")))
                else:
                    teile.append(self._v("b_h_ab",
                        L(f"Nach hinten hast du {menge} Abstand gewonnen, {name} ist {sekunden_sprechen(wert)} weg.", f"You gained {menge} on the car behind, {name} is {sekunden_sprechen(wert)} back."),
                        L(f"Du fährst {name_dat} davon, jetzt {sekunden_sprechen(wert)}.", f"You are pulling away from {name_dat}, now {sekunden_sprechen(wert)}.")))
        return " ".join(teile[:3])

    def _sektoren_nachreichen(self, stand, sag, protokoll):
        """Die Sektorzeiten der letzten Runde kommen über die Zeitnahme kurz nach der Ziellinie."""
        if not self.sektor_warten or protokoll is None or not protokoll.runden:
            return
        zeit_ms, bis = self.sektor_warten
        ich = stand.acc.ich()
        if ich is not None and ich.letzte_runde == zeit_ms and ich.letzte_sektoren and all(ich.letzte_sektoren):
            protokoll.runden[-1]["sektoren"] = list(ich.letzte_sektoren)
            # Die Zeitnahme sagt zuverlässig, ob die Runde ungültig war (Track Limits)
            eintrag = next((r for r in reversed(ich.runden_historie) if r["zeit"] == zeit_ms), None)
            if eintrag is not None and not eintrag["gueltig"] and protokoll.runden[-1]["gueltig"]:
                protokoll.runden[-1]["gueltig"] = False
                try:
                    stand.telemetrie.ungueltig_markieren(zeit_ms)
                except AttributeError:
                    pass
            self.sektor_warten = None
            self._sektor_ansage(stand, sag, protokoll)
        elif time.monotonic() > bis:
            self.sektor_warten = None

    def _sektor_ansage(self, stand, sag, protokoll):
        letzte = protokoll.runden[-1]
        if not letzte["gueltig"] or letzte["box"] or len(protokoll.saubere_runden()) < 3:
            return
        if self.runden - self.sektor_runde < 3:                    # höchstens alle 3 Runden
            return
        # Am besten Kurve für Kurve (aus der Telemetrie), sonst nach Sektoren
        kurven = ri.kurven_analyse(stand)
        if kurven and kurven[0]["verlust"] >= 0.2:
            e = kurven[0]
            self.sektor_runde = self.runden
            grund = acc_telemetrie.grund_text(e)
            menge = _zehntel(e["verlust"])
            sag("sektoren", self._v("kurve",
                L(f"In Kurve {e['kurve']} hast du {menge} verloren", f"You lost {menge} in turn {e['kurve']}") + (L(f", {grund}.", f", {grund}.") if grund else "."),
                L(f"Die Zeit liegt in Kurve {e['kurve']}, {menge}", f"The time is in turn {e['kurve']}, {menge}") + (L(f". Grund: {grund}.", f". Reason: {grund}.") if grund else "."),
                L(f"Schau dir Kurve {e['kurve']} an, dort fehlen {menge}", f"Have a look at turn {e['kurve']}, you are missing {menge} there") + (L(f", {grund}.", f", {grund}.") if grund else ".")))
            return
        verluste = protokoll.sektor_verlust() or []
        if not verluste:
            return
        sektor, verlust = max(verluste, key=lambda paar: paar[1])
        if verlust >= 0.3:
            self.sektor_runde = self.runden
            wort = SEKTOR_WORT.get(sektor, f"{sektor}.")
            sag("sektoren", self._v("sektor",
                L(f"Im {wort} Sektor hast du {_zehntel(verlust)} auf deine Bestzeit verloren.", f"You lost {_zehntel(verlust)} to your best in the {wort} sector."),
                L(f"Die Zeit liegt im {wort} Sektor, da waren es {_zehntel(verlust)}.", f"The time is in the {wort} sector, that was {_zehntel(verlust)}."),
                L(f"Schau mal auf den {wort} Sektor, dort fehlen dir {_zehntel(verlust)}.", f"Have a look at the {wort} sector, you are missing {_zehntel(verlust)} there."),
                L(f"{gross_satz(_zehntel(verlust))} im {wort} Sektor verloren, da geht noch was.", f"{gross_satz(_zehntel(verlust))} lost in the {wort} sector, there is more to find.")))

    def _pace(self, stand, sag, protokoll):
        if protokoll is None or self.runden - self.pace_runde < 5:
            return
        trend = protokoll.trend(5)
        konstanz = protokoll.konstanz(5)
        if trend is not None and trend > 0.15:
            self.pace_runde = self.runden
            menge = _zehntel(trend)
            sag("pace", self._v("pace_ab",
                L(f"Deine Zeiten werden langsamer{self._anrede()}, etwa {menge} pro Runde. Die Reifen bauen ab.", f"Your times are getting slower{self._anrede()}, about {menge} per lap. The tyres are going off."),
                L(f"Die Reifen lassen nach, du verlierst ungefähr {menge} pro Runde. Geh sanfter mit ihnen um.", f"The tyres are fading, you are losing about {menge} per lap. Go easier on them."),
                L(f"Etwa {menge} pro Runde langsamer. Weniger rutschen, dann halten die Reifen länger.", f"About {menge} per lap slower. Less sliding and the tyres will last longer.")))
        elif konstanz and konstanz[0] < 0.35 and self.runden - self.pace_runde >= 8:
            self.pace_runde = self.runden
            menge = _zehntel(konstanz[0])
            sag("pace", self._v("pace_gut",
                L(f"Sehr konstant{self._anrede(0.6)}! Die letzten fünf Runden lagen nur {menge} auseinander.", f"Very consistent{self._anrede(0.6)}! Your last five laps were only {menge} apart."),
                L(f"Wie ein Uhrwerk, nur {menge} Unterschied in fünf Runden.", f"Like clockwork, only {menge} difference over five laps."),
                L(f"Starker Rhythmus{self._anrede(0.6)}, kaum Schwankung.", f"Strong rhythm{self._anrede(0.6)}, hardly any variation.")))
        elif konstanz and konstanz[0] > 1.2:
            self.pace_runde = self.runden
            sag("pace", self._v("pace_schwank",
                L(f"Deine Runden schwanken um {sekunden_sprechen(konstanz[0])}. Such dir einen ruhigeren Rhythmus.", f"Your laps vary by {sekunden_sprechen(konstanz[0])}. Find a calmer rhythm."),
                L(f"Da ist noch viel Unruhe drin, {sekunden_sprechen(konstanz[0])} Unterschied. Lieber sauber als am Limit.", f"Still a lot of variation there, {sekunden_sprechen(konstanz[0])} difference. Better clean than on the limit."),
                L("Versuch, gleichmäßiger zu fahren. Saubere Runden bringen mehr als einzelne schnelle.", "Try to drive more consistently. Clean laps are worth more than the odd fast one.")))

    # --- Qualifying und Training ----------------------------------------------
    def _quali_runde(self, stand, sag, neue_bestzeit, gueltig, war_outlap):
        g, p, acc = stand.grafik, stand.physik, stand.acc
        if neue_bestzeit:
            zeiten = [a.beste_runde for a in acc.autos.values() if gueltige_zeit(a.beste_runde)]
            platz = acc.mein_platz() or g.position
            text = self._v("q_best",
                L(f"Neue Bestzeit{self._anrede()}! {gross_zeit(g.i_beste_zeit)}.", f"New best time{self._anrede()}! {gross_zeit(g.i_beste_zeit)}."),
                L(f"Das war schnell! {gross_zeit(g.i_beste_zeit)}.", f"That was quick! {gross_zeit(g.i_beste_zeit)}."),
                L(f"Persönliche Bestzeit{self._anrede()}. {gross_zeit(g.i_beste_zeit)}.", f"Personal best{self._anrede()}. {gross_zeit(g.i_beste_zeit)}."))
            if zeiten and g.i_beste_zeit <= min(zeiten):
                text += L(" Das ist die schnellste Zeit von allen!", " That is the fastest time of all!")
            elif zeiten:
                text += (L(f" Damit bist du auf Platz {platz}, "
                         f"{sekunden_sprechen((g.i_beste_zeit - min(zeiten)) / 1000)} hinter der Bestzeit.", f" That puts you in P{platz}, "
                         f"{sekunden_sprechen((g.i_beste_zeit - min(zeiten)) / 1000)} off the fastest time."))
            sag("quali", text)
        elif war_outlap:
            temp = _reifen_temp(p)
            if temp is not None and temp >= 70:
                text = L("Die Reifen sind jetzt warm, das ist deine schnelle Runde. Push!", "The tyres are warm now, this is your push lap. Push!")
            else:
                text = L("Die Reifen sind noch nicht ganz warm, fahr noch eine Runde zum Aufwärmen.", "The tyres aren't quite warm yet, do one more warm-up lap.")
            auto, sekunden, _ = ri.strecken_nachbar(stand, "vorne")
            if auto is not None and sekunden is not None and sekunden < 3:
                text += (L(f" Achtung, vor dir ist {name_von(auto)} nur {sekunden_sprechen(sekunden)} entfernt, "
                         f"lass dir etwas mehr Platz.", f" Heads up, {name_von(auto)} is only {sekunden_sprechen(sekunden)} ahead of you, "
                         f"give yourself a bit more room."))
            sag("quali", text)
        elif gueltig and gueltige_zeit(g.i_letzte_zeit) and gueltige_zeit(g.i_beste_zeit):
            delta = (g.i_letzte_zeit - g.i_beste_zeit) / 1000
            if 0 < delta < 3:
                sag("quali", L(f"Die Runde war {_zehntel(delta)} langsamer als deine Bestzeit.", f"That lap was {_zehntel(delta)} slower than your best."))
        elif not gueltig:
            sag("quali", L("Die Runde war leider ungültig, Track Limits.", "Unfortunately the lap was invalid, track limits."))

        # Wie viele Runden passen noch in die Session?
        rundenzeit = (g.i_beste_zeit or g.i_letzte_zeit) / 1000 if gueltige_zeit(g.i_beste_zeit or g.i_letzte_zeit) else None
        if rundenzeit and g.session_rest > 0:
            moeglich = int((g.session_rest / 1000) // rundenzeit) + 1
            if moeglich != self.quali_restrunden and moeglich in (1, 2):
                sag("quali", L("Das ist deine letzte Chance auf eine schnelle Runde, gib alles!", "This is your last chance for a fast lap, give it everything!") if moeglich == 1
                    else L("Die Zeit reicht noch für zwei Runden.", "There's still time for two laps."))
            self.quali_restrunden = moeglich

    # --- Sprit und Box ------------------------------------------------------------
    def _sprit_und_box(self, stand, sag, rennen):
        lage = sprit_lage(stand)
        if lage is None:
            return
        _, restrunden, e = lage
        reicht = e["reicht_runden"]
        volle_runden = math.floor(reicht)
        box_gesagt_jetzt = False

        # Boxenfenster und "Box, Box" (nur im Rennen mit bekannter Dauer)
        if rennen and restrunden is not None:
            if e["stopps"] >= 1:
                self.stopp_war_noetig = True
                menge = e["menge_pro_stopp"]
                runde = e["aktuelle_runde"]
                if not self.box_gesagt and runde >= e["fenster_bis"] and volle_runden >= 1:
                    self.box_gesagt = self.fenster_gesagt = box_gesagt_jetzt = True
                    sag("box", self._v("boxbox",
                        L(f"Box, Box{self._anrede(0.5)}! Komm diese Runde an die Box und tanke {menge} Liter nach.", f"Box, box{self._anrede(0.5)}! Box this lap and add {menge} litres."),
                        L(f"Box diese Runde{self._anrede(0.5)}, Box diese Runde. Wir tanken {menge} Liter.", f"Box this lap{self._anrede(0.5)}, box this lap. We add {menge} litres."),
                        L(f"Box, Box! {menge} Liter, wir sind bereit für dich.", f"Box, box! {menge} litres, we're ready for you."))
                        + boxenmenue_hinweis(stand, menge) + self._rauskommen_satz(stand), True)
                elif not self.fenster_gesagt and e["fenster_von"] <= runde < e["fenster_bis"]:
                    self.fenster_gesagt = True
                    sag("box", L(f"Das Boxenfenster ist jetzt offen. Wir brauchen {menge} Liter, "
                               f"und du solltest spätestens in Runde {e['fenster_bis']} reinkommen.", f"The pit window is open now. We need {menge} litres, "
                               f"and you should come in by lap {e['fenster_bis']} at the latest.")
                        + boxenmenue_hinweis(stand, menge) + self._rauskommen_satz(stand))
            elif self.stopp_war_noetig:
                self.stopp_war_noetig = False
                sag("box", self._v("sprit_reicht",
                    L("Gute Nachricht, der Sprit reicht jetzt bis ins Ziel.", "Good news, the fuel now gets you to the finish."),
                    L("Sprit ist kein Thema mehr, das reicht bis zur Zielflagge.", "Fuel is no longer an issue, you'll make the flag."),
                    L("Wir sind beim Sprit auf der sicheren Seite. Volle Attacke ist erlaubt.", "We're safe on fuel. Full attack is allowed.")))

        # Sprit-Warnungen: noch 3, 2, 1 Runden
        sprit_knapp = restrunden is None or e["stopps"] > 0
        if sprit_knapp and volle_runden <= 3 and volle_runden not in self.sprit_gewarnt:
            self.sprit_gewarnt.update(range(volle_runden, 4))
            if box_gesagt_jetzt and self.an.get("box"):
                return                      # "Box, Box" sagt schon alles
            if volle_runden >= 2:
                n = L("drei", "three") if volle_runden == 3 else L("zwei", "two")
                sag("sprit", self._v("sprit", L(f"Der Sprit reicht nur noch für {n} Runden.", f"Fuel only lasts for {n} more laps."),
                                     L(f"Noch {n} Runden Sprit im Tank.", f"{n} laps of fuel left in the tank."),
                                     L(f"Sprit wird knapp, noch {n} Runden.", f"Fuel is getting low, {n} laps left.")))
            elif volle_runden == 1:
                sag("sprit", L("Der Sprit reicht nur noch für eine Runde! Komm diese Runde an die Box.", "Fuel only lasts for one more lap! Box this lap."), True)
            else:
                sag("sprit", L("Der Sprit reicht nicht mehr für eine ganze Runde!", "The fuel won't last a full lap anymore!"), True)

    def _rauskommen_satz(self, stand):
        """' Du kommst dann ungefähr auf Platz 6 raus, hinter Müller.'"""
        if not self.an.get("box_begleitung") or stand.acc.verbindungs_id is None:
            return ""
        ergebnis = wiedereinstieg(stand.acc, boxenverlust(stand.acc))
        if not ergebnis:
            return ""
        platz, vorne, hinten = ergebnis
        text = L(f" Nach dem Stopp kommst du ungefähr auf Platz {platz} raus", f" After the stop you will rejoin around P{platz}")
        if vorne:
            text += L(f", etwa {sekunden_sprechen(max(0.1, vorne[1]))} hinter {name_von(vorne[0], 'dat', mit_platz=False)}{jetzt_auf(vorne[0])}", f", about {sekunden_sprechen(max(0.1, vorne[1]))} behind {name_von(vorne[0], 'dat', mit_platz=False)}{jetzt_auf(vorne[0])}")
        return text + "."

    # --- Boxengasse -------------------------------------------------------------
    def _boxengasse(self, stand, sag, rennen, protokoll, jetzt):
        g, p = stand.grafik, stand.physik
        rein = g.in_boxengasse and not self.in_boxengasse
        raus = not g.in_boxengasse and self.in_boxengasse
        if rein:
            self.boxengasse_seit = jetzt
            self.limiter_gesagt = False
            if rennen and protokoll is not None:
                protokoll.stopps += 1
            if rennen:
                text = self._v("boxengasse",
                    L(f"Okay{self._anrede(0.6)}, du bist in der Boxengasse.", f"Okay{self._anrede(0.6)}, you're in the pit lane."),
                    L("Boxengasse, Copy. Wir sind bereit.", "Pit lane, copy. We're ready for you."),
                    L(f"Willkommen in der Box{self._anrede(0.6)}. Sauber auf die Markierung.", f"Welcome in{self._anrede(0.6)}. Nice and clean onto the marks."))
                if not p.pitlimiter:
                    text += L(" Pitlimiter an!", " Pit limiter on!")
                lage = sprit_lage(stand)
                if lage and lage[1] is not None and lage[2]["stopps"] >= 1:
                    menge = lage[2]["menge_pro_stopp"]
                    text += L(f" Wir tanken {menge} Liter.", f" We refuel {menge} litres.") + boxenmenue_hinweis(stand, menge)
                elif lage and lage[1] is not None:
                    text += L(" Sprit brauchen wir eigentlich keinen mehr.", " We don't really need any more fuel.")
                if self.an.get("reifendruck"):
                    druck = druck_text(stand, kurz=True)
                    if druck:
                        text += " " + druck
                sag("box_begleitung", text)
                if not p.pitlimiter:
                    self.limiter_gesagt = True          # schon im Satz enthalten
        if raus:
            if rennen:
                self.ausfahrt_faellig = jetzt + 2       # kurz warten, bis die Position stimmt
            else:
                self.outlap = True
                sag("quali", L(f"Outlap{self._anrede(0.6)}. Bring die Reifen auf Temperatur.", f"Out lap{self._anrede(0.6)}. Get the tyres up to temperature."))
        self.in_boxengasse = g.in_boxengasse

        if (g.in_boxengasse and not p.pitlimiter and not self.limiter_gesagt
                and jetzt - self.boxengasse_seit < 4 and p.tempo_kmh > 40):
            self.limiter_gesagt = True
            sag("pitlimiter", self._v("limiter",
                L("Pitlimiter! Schalte den Pitlimiter ein!", "Pit limiter! Pit limiter on!"),
                L("Limiter, Limiter! Sonst gibt es eine Strafe.", "Limiter, limiter! Or you'll get a penalty.")), True)

        if self.ausfahrt_faellig and jetzt >= self.ausfahrt_faellig:
            self.ausfahrt_faellig = None
            acc = stand.acc
            platz = acc.mein_platz() or g.position
            text = self._v("raus",
                L(f"Du bist wieder draußen auf Platz {platz}.", f"You're back out in P{platz}."),
                L(f"Guter Stopp. Du kommst auf Platz {platz} wieder raus.", f"Good stop. You rejoin in P{platz}."),
                L(f"Und raus, Platz {platz}.", f"And out, P{platz}."))
            vorne, sek_vorne, _ = ri.strecken_nachbar(stand, "vorne")
            hinten, sek_hinten, _ = ri.strecken_nachbar(stand, "hinten")
            if vorne is not None and sek_vorne is not None and sek_vorne < 10:
                text += L(f" Vor dir auf der Strecke ist {name_von(vorne)}, {sekunden_sprechen(sek_vorne)} entfernt.", f" Ahead of you on track is {name_von(vorne)}, {sekunden_sprechen(sek_vorne)} away.")
            if hinten is not None and sek_hinten is not None and sek_hinten < 5:
                text += L(f" Hinter dir kommt {name_von(hinten)} mit {sekunden_sprechen(sek_hinten)} Abstand.", f" Behind you comes {name_von(hinten)} with a gap of {sekunden_sprechen(sek_hinten)}.")
            temp = _reifen_temp(p)
            if temp is None or temp < 65:
                text += L(" Die Reifen sind noch kalt, sei in den ersten Kurven vorsichtig.", " The tyres are still cold, be careful in the first corners.")
            sag("box_begleitung", text)

    # --- Gegner an der Box ------------------------------------------------------
    def _gegner_box(self, stand, sag):
        acc = stand.acc
        neue = [e for e in acc.box_ereignisse if e[0] > self.box_ereignis_zeit]
        if not neue:
            return
        self.box_ereignis_zeit = neue[-1][0]
        ich = acc.ich()
        liste = acc.rangliste()
        if ich is None or ich not in liste:
            return
        mein_platz = liste.index(ich) + 1
        lage = sprit_lage(stand)
        muss_stoppen = bool(lage and lage[1] is not None and lage[2]["stopps"] >= 1)
        fenster_offen = bool(muss_stoppen and lage[2]["aktuelle_runde"] >= lage[2]["fenster_von"])
        for _, index, art, _ in neue:
            auto = acc.autos.get(index)
            if auto is None or auto is ich or auto not in liste:
                continue
            platz = liste.index(auto) + 1
            if abs(platz - mein_platz) > 2 or not self._frei(f"gegnerbox{index}{art}", 30):
                continue
            name = name_von(auto)
            Name, name_dat, name_akk = gross_satz(name), name_von(auto, "dat"), name_von(auto, "akk")
            if art == "rein":
                text = L(f"{Name} fährt gerade an die Box.", f"{Name} is pitting right now.")
                if platz > mein_platz and fenster_offen:
                    text += L(" Achtung, das könnte ein Undercut sein. Überleg, ob du nächste Runde reinkommst.", " Heads up, that could be an undercut. Think about coming in next lap.")
                elif platz < mein_platz and fenster_offen:
                    text += (L(" Wenn du jetzt ein, zwei schnelle Runden fährst und dann reinkommst, "
                             "kannst du vor ihm rauskommen.", " If you do one or two fast laps now and then come in, "
                             "you can rejoin ahead of him."))
                elif platz < mein_platz and not muss_stoppen:
                    art_abstand, wert = acc.abstand_zu(auto)
                    if art_abstand == "sek" and wert is not None and wert < boxenverlust(acc):
                        text += L(" Du musst nicht mehr stoppen, er wird wahrscheinlich hinter dir rauskommen.", " You don't need to stop anymore, he will probably rejoin behind you.")
                sag("gegner_box", text)
            else:
                art_abstand, wert = acc.abstand_zu(auto)
                if art_abstand == "sek" and wert is not None:
                    wo = L("vor dir", "ahead of you") if wert > 0 else L("hinter dir", "behind you")
                    sag("gegner_box", L(f"{Name} ist wieder draußen und jetzt {sekunden_sprechen(abs(wert))} {wo}.", f"{Name} is back out and now {sekunden_sprechen(abs(wert))} {wo}."))

    # --- Verkehr ----------------------------------------------------------------
    def _verkehr(self, stand, sag):
        g = stand.grafik
        if g.in_boxengasse or g.runden_fertig < 1:
            return
        auto, sekunden, runden = ri.strecken_nachbar(stand, "hinten")
        if auto is not None and sekunden is not None and runden > 0 and sekunden < 2.5:
            if self._frei(f"ueberrunder{auto.index}", 90):
                name = name_von(auto)
                Name, name_dat, name_akk = gross_satz(name), name_von(auto, "dat"), name_von(auto, "akk")
                sag("verkehr", self._v("ueberrunder",
                    L(f"Achtung, {name} kommt von hinten und will dich überrunden. Lass ihn sauber vorbei.", f"Heads up, {name} is coming from behind and wants to lap you. Let him by cleanly."),
                    L(f"Schnelleres Auto hinter dir, {name}. Er ist eine Runde vor dir, mach ihm Platz.", f"Faster car behind you, {name}. He is a lap ahead of you, make room for him."),
                    L(f"{Name} überrundet dich gleich, {sekunden_sprechen(sekunden)} hinter dir. Kein Kampf, lass ihn ziehen.", f"{Name} is about to lap you, {sekunden_sprechen(sekunden)} behind you. No fight, let him go.")))
        auto, sekunden, runden = ri.strecken_nachbar(stand, "vorne")
        if auto is not None and sekunden is not None and runden < 0 and sekunden < 4:
            if self._frei(f"ueberrundet{auto.index}", 90):
                name = name_von(auto)
                Name, name_dat, name_akk = gross_satz(name), name_von(auto, "dat"), name_von(auto, "akk")
                sag("verkehr", self._v("ueberrundet",
                    L(f"Vor dir ist ein überrundetes Auto, {name}, {sekunden_sprechen(sekunden)} vor dir. Plan das Überholen ein.", f"There is a lapped car ahead of you, {name}, {sekunden_sprechen(sekunden)} ahead. Plan the overtake."),
                    L(f"Überrundeter vor dir, {name}. Such dir eine saubere Stelle zum Vorbeigehen.", f"Backmarker ahead, {name}. Find a clean place to get by."),
                    L(f"Verkehr vorne, {name} liegt eine Runde zurück. Verlier dort nicht zu viel Zeit.", f"Traffic ahead, {name} is a lap down. Don't lose too much time there.")))

    # --- Wetter -----------------------------------------------------------------
    def _wetter(self, stand, sag):
        g = stand.grafik
        if self.regen_10 is not None and g.regen_10min != self.regen_10 and self._frei("regen", 60):
            if g.regen_10min > g.regen:
                sag("wetter", L(f"In etwa 10 Minuten wird {REGEN_NAMEN[min(g.regen_10min, 5)]} erwartet.", f"In about 10 minutes {REGEN_NAMEN[min(g.regen_10min, 5)]} is expected."))
            elif g.regen_10min < g.regen:
                sag("wetter", L("Der Regen wird in etwa 10 Minuten nachlassen.", "The rain will ease off in about 10 minutes."))
        elif (self.regen_30 is not None and g.regen_30min != self.regen_30
              and g.regen_30min > g.regen_10min and self._frei("regen30", 120)):
            sag("wetter", L(f"In etwa 30 Minuten ist {REGEN_NAMEN[min(g.regen_30min, 5)]} angesagt.", f"In about 30 minutes {REGEN_NAMEN[min(g.regen_30min, 5)]} is forecast."))
        self.regen_10, self.regen_30 = g.regen_10min, g.regen_30min

        # Regen-Strategie: passen die Reifen noch?
        empfehlung = regen_empfehlung(stand)
        if empfehlung and self._frei("regenstrategie", 150):
            sag("regen_strategie", empfehlung)

    # --- Positionen und Duelle ------------------------------------------------------
    def _positionen(self, stand, sag, jetzt):
        g = stand.grafik
        acc = stand.acc
        platz = acc.mein_platz()
        if platz is None:
            return

        # Position erst ansagen, wenn sie 2,5 Sekunden stabil ist
        if platz != self.platz_kandidat:
            self.platz_kandidat, self.platz_seit = platz, jetzt
        elif platz != self.platz and jetzt - self.platz_seit >= 2.5:
            if self.platz is not None and not g.in_boxengasse and self._frei("platz", 4):
                if platz < self.platz:
                    sag("positionen", mit_zuspruch(self._v("platz_auf",
                        L(f"Du hast eine Position gewonnen und liegst jetzt auf Platz {platz}.", f"You gained a position and are now in P{platz}."),
                        L(f"Sauber vorbei! Platz {platz}.", f"Clean move! P{platz}."),
                        L(f"Platz {platz}, gut gemacht{self._anrede()}!", f"P{platz}, well done{self._anrede()}!"),
                        L(f"Einen Platz gewonnen, du bist jetzt Platz {platz}.", f"One place gained, you are now P{platz}.")), stand, wahrscheinlichkeit=0.35))
                else:
                    sag("positionen", mit_zuspruch(self._v("platz_ab",
                        L(f"Du hast eine Position verloren und liegst jetzt auf Platz {platz}.", f"You lost a position and are now in P{platz}."),
                        L(f"Er ist vorbei, du bist jetzt Platz {platz}.", f"He's through, you are now P{platz}."),
                        L(f"Platz {platz} jetzt. Bleib dran, das holen wir zurück.", f"P{platz} now. Stay on him, we'll get that back.")), stand, wahrscheinlichkeit=0.35))
            self.platz = platz

        # Duelle: erst ab der zweiten Runde, beim Start sind alle dicht beisammen
        if g.runden_fertig < 1 or g.in_boxengasse:
            return
        if platz > 1:
            art, wert = acc.abstand_zu(acc.auto_auf_platz(platz - 1))
            if art == "sek" and wert is not None and wert > 0:
                if wert < 1.0 and not self.vorne_nah:
                    self.vorne_nah = True
                    if self._frei("vorne", 120):
                        sag("duelle", mit_zuspruch(self._v("duell_v",
                            L(f"Du bist dicht am Vordermann dran, nur noch {sekunden_sprechen(wert)}.", f"You're close to the car ahead, only {sekunden_sprechen(wert)}."),
                            L(f"Du klebst am Vordermann, nur {sekunden_sprechen(wert)}. Such dir die Lücke.", f"You're glued to the car ahead, only {sekunden_sprechen(wert)}. Look for the gap."),
                            L(f"{gross_satz(sekunden_sprechen(wert))} zum Vordermann, jetzt wird's interessant.", f"{gross_satz(sekunden_sprechen(wert))} to the car ahead, now it's getting interesting.")),
                            stand, wahrscheinlichkeit=0.5))
                elif wert > 1.5:
                    self.vorne_nah = False
        hinten = acc.auto_auf_platz(platz + 1)
        if hinten:
            art, wert = acc.abstand_zu(hinten)
            if art == "sek" and wert is not None and wert < 0:
                if -wert < 1.0 and not self.hinten_nah:
                    self.hinten_nah = True
                    if self._frei("hinten", 120):
                        sag("duelle", mit_zuspruch(self._v("duell_h",
                            L(f"Achtung, der Hintermann ist nur noch {sekunden_sprechen(-wert)} hinter dir.", f"Heads up, the car behind is only {sekunden_sprechen(-wert)} behind you."),
                            L(f"Der Hintermann ist dran, {sekunden_sprechen(-wert)}.", f"The car behind is on you, {sekunden_sprechen(-wert)}."),
                            L(f"Hinten wird's eng, {sekunden_sprechen(-wert)}. Sauber bleiben.", f"It's getting tight behind, {sekunden_sprechen(-wert)}. Stay clean.")),
                            stand, wahrscheinlichkeit=0.5))
                elif -wert > 1.5:
                    self.hinten_nah = False


def gross_satz(text):
    return text[:1].upper() + text[1:]


def gross_zeit(ms):
    """'Du bist 2 Minuten 17,9 Sekunden gefahren' -> als Satzanfang groß."""
    return L("Du bist ", "You did ") + zeit_sprechen(ms) + L(" gefahren", "")
