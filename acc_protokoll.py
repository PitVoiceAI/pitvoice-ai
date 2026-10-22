# acc_protokoll.py
# Das Rennprotokoll: schreibt jede Runde mit und wertet sie aus.
#   - Konstanz (wie gleichmäßig du fährst) und Reifenabbau (werden die Runden langsamer?)
#   - Sektoren: wo du Zeit verlierst
#   - Zeitverlust beim Boxenstopp und wo du nach dem Stopp wieder rauskommst
#   - Debrief nach dem Rennen, wird auch als Datei gespeichert
#
# Diese Datei startet man nicht selbst.

import json
import os
import time
from acc_sprache import L, englisch, komma

ORDNER = os.path.dirname(os.path.abspath(__file__))
RENNEN_ORDNER = os.path.join(ORDNER, "rennen")
SESSION_NAMEN = {0: "Training", 1: "Qualifying", 2: "Rennen"}


def _zahl(wert, stellen=1):
    return komma(wert, stellen)


def _zeit(ms):
    sekunden = ms / 1000
    minuten = int(sekunden // 60)
    rest = sekunden - minuten * 60
    if minuten:
        if englisch():
            return f"{minuten} {'minute' if minuten == 1 else 'minutes'} {_zahl(rest)} seconds"
        return f"{minuten} {'Minute' if minuten == 1 else 'Minuten'} {_zahl(rest)} Sekunden"
    return f"{_zahl(rest)} {L('Sekunden', 'seconds')}"


_SEKTOR = {1: L("ersten", "first"), 2: L("zweiten", "second"), 3: L("dritten", "third")}


def englisch_session(nummer):
    return {0: "Practice", 1: "Qualifying", 2: "Race"}.get(nummer, "Session")


def _sek(wert):
    if _zahl(wert) in ("1,0", "1.0"):
        return L("1 Sekunde", "1 second")
    return f"{_zahl(wert)} {L('Sekunden', 'seconds')}"


class Protokoll:
    def __init__(self):
        self.neu("", -1, "")

    def neu(self, strecke, session, auto):
        self.strecke = strecke
        self.session = session
        self.auto = auto
        self.beginn = time.time()
        self.runden = []          # je Runde: dict (siehe runde_eintragen)
        self.startplatz = None
        self.endplatz = None
        self.stopps = 0
        self.strafen = 0
        self.ende_gemeldet = False
        self.gespeichert = False
        self.telemetrie = None        # wird vor dem Speichern gesetzt
        self.aufgegeben = False       # Rennen über das Menü beendet (Auto abgestellt)
        self.karte = None             # Umriss der Strecke [(x, y), ...], wird vor dem Speichern gesetzt

    # --- Mitschreiben -----------------------------------------------------
    def runde_eintragen(self, nummer, zeit_ms, gueltig, mit_box, platz, tank, sektoren):
        if not zeit_ms or zeit_ms <= 0 or zeit_ms > 10_000_000:
            return
        if self.runden and self.runden[-1]["nummer"] == nummer:
            return
        self.runden.append({"nummer": nummer, "zeit": zeit_ms, "gueltig": bool(gueltig),
                            "box": bool(mit_box), "platz": platz, "tank": round(tank, 1),
                            "sektoren": list(sektoren or [])})

    def saubere_runden(self, anzahl=None):
        """Runden ohne Boxenbesuch, gültig und nicht die erste Runde (Start)."""
        sauber = [r for r in self.runden if r["gueltig"] and not r["box"] and r["nummer"] > 1]
        return sauber[-anzahl:] if anzahl else sauber

    def bestzeit(self):
        zeiten = [r["zeit"] for r in self.runden if r["gueltig"]]
        return min(zeiten) if zeiten else None

    # --- Auswertungen -----------------------------------------------------
    def konstanz(self, anzahl=5):
        """(Spanne in Sekunden, Durchschnitt in ms) der letzten sauberen Runden, oder None."""
        runden = self.saubere_runden(anzahl)
        if len(runden) < anzahl:
            return None
        zeiten = [r["zeit"] for r in runden]
        return (max(zeiten) - min(zeiten)) / 1000, sum(zeiten) / len(zeiten)

    def trend(self, anzahl=6):
        """Um wie viele Sekunden pro Runde du zuletzt langsamer (+) oder schneller (-) wirst."""
        runden = self.saubere_runden(anzahl)
        if len(runden) < anzahl:
            return None
        n = len(runden)
        xs = list(range(n))
        ys = [r["zeit"] / 1000 for r in runden]
        mx, my = sum(xs) / n, sum(ys) / n
        nenner = sum((x - mx) ** 2 for x in xs)
        return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / nenner if nenner else None

    def beste_sektoren(self):
        """Deine beste Zeit in jedem Sektor (aus allen gültigen Runden)."""
        beste = []
        for runde in self.runden:
            if not runde["gueltig"]:
                continue
            for i, zeit in enumerate(runde["sektoren"]):
                if zeit:
                    if i >= len(beste):
                        beste.append(zeit)
                    elif beste[i] is None or zeit < beste[i]:
                        beste[i] = zeit
        return beste

    def sektor_verlust(self):
        """Vergleicht die letzte Runde mit deinen besten Sektoren.
        Gibt eine Liste (sektor_nummer, verlust_in_sekunden) zurück, oder None."""
        if not self.runden or not self.runden[-1]["sektoren"]:
            return None
        beste = self.beste_sektoren()
        letzte = self.runden[-1]["sektoren"]
        ergebnis = []
        for i, zeit in enumerate(letzte):
            if zeit and i < len(beste) and beste[i]:
                ergebnis.append((i + 1, (zeit - beste[i]) / 1000))
        return ergebnis or None

    def zusammenfassung(self):
        """Alles Wichtige als Wörterbuch (für das Fenster und den Debrief)."""
        konstanz = self.konstanz(min(5, max(3, len(self.saubere_runden()))))
        return {
            "strecke": self.strecke, "session": SESSION_NAMEN.get(self.session, "Session"),
            "auto": self.auto, "beginn": self.beginn, "startplatz": self.startplatz,
            "endplatz": self.endplatz, "stopps": self.stopps, "strafen": self.strafen,
            "bestzeit": self.bestzeit(), "runden": list(self.runden),
            "konstanz": konstanz[0] if konstanz else None, "aufgegeben": self.aufgegeben,
            "trend": self.trend(),
        }

    # --- Debrief ----------------------------------------------------------
    def analyse(self, rueckstand_pole=None):
        """Die Zahlen für die Rede nach der Session: Stärken und wo noch Zeit liegt."""
        a = {"rennen": self.session == 2, "startplatz": self.startplatz, "endplatz": self.endplatz,
             "runden": self.runden[-1]["nummer"] if self.runden else 0, "stopps": self.stopps, "strafen": self.strafen,
             "rueckstand_pole": rueckstand_pole}
        best = self.bestzeit()
        a["bestzeit"] = best
        a["best_runde"] = next((r["nummer"] for r in self.runden if r["gueltig"] and r["zeit"] == best), None)
        a["ungueltig"] = sum(1 for r in self.runden if not r["gueltig"] and r["nummer"] > 1)
        sauber = self.saubere_runden()
        a["saubere"] = len(sauber)
        a["schnitt"] = sum(r["zeit"] for r in sauber) / len(sauber) if sauber else None
        k = self.konstanz(min(5, max(3, len(sauber)))) if len(sauber) >= 3 else None
        a["spanne"] = k[0] if k else None
        a["trend"] = self.trend(min(8, len(sauber))) if len(sauber) >= 5 else None
        # Bestzeit spät im Rennen gefahren? Dann warst du hinten raus stark.
        a["best_spaet"] = bool(best and a["best_runde"] and len(self.runden) >= 6
                               and a["best_runde"] > self.runden[-1]["nummer"] * 0.6)
        # Welcher Sektor kostet im Schnitt am meisten gegenüber deinem besten Sektor?
        beste = self.beste_sektoren()
        verluste = []
        for i in range(len(beste)):
            werte = [r["sektoren"][i] for r in sauber if len(r["sektoren"]) > i and r["sektoren"][i]]
            if beste[i] and len(werte) >= 3:
                verluste.append(((sum(werte) / len(werte) - beste[i]) / 1000, i + 1))
        verluste.sort(reverse=True)
        a["sektor_verlust"] = verluste[0] if verluste and verluste[0][0] >= 0.15 else None
        a["sektor_stark"] = verluste[-1] if len(verluste) >= 2 and verluste[-1][0] < 0.15 else None
        # Theoretische Bestzeit aus den besten Sektoren
        a["ideal"] = sum(beste) if beste and len(beste) == 3 and all(beste) else None
        return a

    def fakten_text(self, rueckstand_pole=None, fahrer=""):
        """Die Analyse als Stichpunkte für die KI."""
        a = self.analyse(rueckstand_pole)
        z = []
        z.append(L("Session: ", "Session: ") + (L("Rennen", "Race") if a["rennen"] else
                                                 L(SESSION_NAMEN.get(self.session, "Session"), englisch_session(self.session))))
        if fahrer:
            z.append(L(f"Fahrer: {fahrer}", f"Driver: {fahrer}"))
        if a["startplatz"]:
            z.append(L(f"Startplatz: {a['startplatz']}", f"Grid position: {a['startplatz']}"))
        if a["endplatz"]:
            z.append(L(f"Ergebnis: Platz {a['endplatz']}", f"Result: P{a['endplatz']}"))
        if self.aufgegeben:
            z.append(L("Rennen vorzeitig beendet (Auto abgestellt)", "Retired early (car parked)"))
        z.append(L(f"Gefahrene Runden: {a['runden']}", f"Laps driven: {a['runden']}"))
        if a["bestzeit"]:
            z.append(L(f"Schnellste Runde: {_zeit(a['bestzeit'])} in Runde {a['best_runde']}",
                       f"Fastest lap: {_zeit(a['bestzeit'])} on lap {a['best_runde']}"))
        if a["ideal"] and a["bestzeit"] and a["bestzeit"] - a["ideal"] > 100:
            z.append(L(f"Aus deinen besten Sektoren zusammen wären {_zeit(a['ideal'])} möglich, "
                       f"also {_sek((a['bestzeit'] - a['ideal']) / 1000)} schneller als deine Bestzeit",
                       f"Your best sectors combined would give {_zeit(a['ideal'])}, "
                       f"{_sek((a['bestzeit'] - a['ideal']) / 1000)} quicker than your best lap"))
        if a["schnitt"]:
            z.append(L(f"Durchschnitt der sauberen Runden: {_zeit(a['schnitt'])}", f"Average of clean laps: {_zeit(a['schnitt'])}"))
        if a["spanne"] is not None:
            z.append(L(f"Konstanz: die letzten sauberen Runden lagen {_sek(a['spanne'])} auseinander "
                       f"(unter 0,5 sehr gut, über 1,2 schwankend)",
                       f"Consistency: the last clean laps were {_sek(a['spanne'])} apart "
                       f"(below 0.5 very good, above 1.2 inconsistent)"))
        if a["trend"] is not None:
            if a["trend"] > 0.12:
                z.append(L(f"Gegen Ende pro Runde etwa {_sek(a['trend'])} langsamer geworden (Reifen oder Konzentration)",
                           f"Got about {_sek(a['trend'])} slower per lap towards the end (tyres or focus)"))
            elif a["trend"] < -0.12:
                z.append(L(f"Gegen Ende pro Runde etwa {_sek(-a['trend'])} schneller geworden",
                           f"Got about {_sek(-a['trend'])} faster per lap towards the end"))
        if a["best_spaet"]:
            z.append(L("Die Bestzeit kam spät in der Session", "The best lap came late in the session"))
        if a["sektor_verlust"]:
            v, nr = a["sektor_verlust"]
            z.append(L(f"Größtes Potenzial: Sektor {nr}, dort im Schnitt {_sek(v)} langsamer als dein bester Sektor {nr}",
                       f"Biggest potential: sector {nr}, on average {_sek(v)} slower there than your best sector {nr}"))
        if a["sektor_stark"]:
            z.append(L(f"Stärkster, konstantester Sektor: Sektor {a['sektor_stark'][1]}",
                       f"Strongest, most consistent sector: sector {a['sektor_stark'][1]}"))
        if a["ungueltig"]:
            z.append(L(f"Ungültige Runden (Track Limits): {a['ungueltig']}", f"Invalid laps (track limits): {a['ungueltig']}"))
        if a["rennen"]:
            z.append(L(f"Boxenstopps: {a['stopps']}", f"Pit stops: {a['stopps']}"))
        z.append(L(f"Strafen: {a['strafen']}", f"Penalties: {a['strafen']}"))
        if a["rueckstand_pole"]:
            z.append(L(f"Rückstand auf die schnellste Zeit der Session: {_sek(a['rueckstand_pole'])}",
                       f"Gap to the fastest time of the session: {_sek(a['rueckstand_pole'])}"))
        return "\n".join("- " + t for t in z)

    def debrief(self, fahrer="", rueckstand_pole=None):
        """Die Rede nach der Session (ohne KI): Ergebnis, Lob, wo noch Zeit liegt, Abschluss."""
        anrede = f", {fahrer}" if fahrer else ""
        a = self.analyse(rueckstand_pole)
        teile = []
        lob = []
        luft = []
        # --- Ergebnis ---
        if a["rennen"]:
            if a["endplatz"]:
                if a["endplatz"] == 1:
                    teile.append(L(f"Das ist der Sieg{anrede}! Großartige Arbeit heute.", f"That's the win{anrede}! Fantastic job today."))
                elif a["endplatz"] <= 3:
                    teile.append(L(f"Podium{anrede}! Platz {a['endplatz']}, klasse gefahren.", f"Podium{anrede}! P{a['endplatz']}, great drive."))
                else:
                    teile.append(L(f"Das war's{anrede}, du bringst das Auto auf Platz {a['endplatz']} ins Ziel.",
                                   f"That's it{anrede}, you bring the car home in P{a['endplatz']}."))
                if a["startplatz"]:
                    diff = a["startplatz"] - a["endplatz"]
                    if diff > 0:
                        lob.append(L(f"Von Platz {a['startplatz']} aus {'einen Platz' if diff == 1 else f'{diff} Plätze'} gutgemacht, starke Aufholjagd.",
                                     f"Gained {'one place' if diff == 1 else f'{diff} places'} from P{a['startplatz']}, strong comeback."))
                    elif diff == 0 and a["endplatz"] <= 5:
                        lob.append(L("Du hast deine Position die ganze Zeit sauber verteidigt.", "You defended your position cleanly the whole way."))
                    elif diff < 0:
                        luft.append(L(f"Wir haben {'einen Platz' if diff == -1 else f'{-diff} Plätze'} gegenüber dem Start verloren, das holen wir uns nächstes Mal zurück.",
                                      f"We lost {'one place' if diff == -1 else f'{-diff} places'} from the start, we'll get that back next time."))
            else:
                teile.append(L(f"Das Rennen ist vorbei{anrede}.", f"The race is over{anrede}."))
        else:
            teile.append(L(f"Die Session ist vorbei{anrede}.", f"The session is over{anrede}."))
            if a["endplatz"]:
                teile.append(L(f"Du stehst auf Platz {a['endplatz']}.", f"You're in P{a['endplatz']}."))
            if a["rueckstand_pole"]:
                teile.append(L(f"Auf die schnellste Zeit fehlen dir {_sek(a['rueckstand_pole'])}.", f"You're {_sek(a['rueckstand_pole'])} off the fastest time."))
        # --- Lob ---
        if a["bestzeit"]:
            satz = L(f"Deine schnellste Runde war {_zeit(a['bestzeit'])}", f"Your fastest lap was {_zeit(a['bestzeit'])}")
            satz += L(", und die kam spät, das zeigt, dass du hinten raus noch zulegen konntest." if a["best_spaet"] else ".",
                      ", and it came late, which shows you could still find pace at the end." if a["best_spaet"] else ".")
            lob.append(satz)
        if a["spanne"] is not None and a["spanne"] < 0.5:
            lob.append(L(f"Deine Runden lagen nur {_sek(a['spanne'])} auseinander, das war richtig konstant.",
                         f"Your laps were only {_sek(a['spanne'])} apart, that was really consistent."))
        elif a["spanne"] is not None and a["spanne"] < 1.0:
            lob.append(L("Die Konstanz war ordentlich.", "Consistency was decent."))
        if a["sektor_stark"]:
            lob.append(L(f"Im {_SEKTOR[a['sektor_stark'][1]]} Sektor warst du Runde für Runde sehr sauber.",
                         f"In sector {a['sektor_stark'][1]} you were very tidy lap after lap."))
        if a["strafen"] == 0 and a["ungueltig"] == 0 and a["runden"] >= 5:
            lob.append(L("Keine Strafe und keine ungültige Runde, sauber gefahren.", "No penalty and no invalid lap, clean driving."))
        # --- Wo noch Zeit liegt ---
        if a["sektor_verlust"]:
            v, nr = a["sektor_verlust"]
            luft.append(L(f"Das meiste Potenzial liegt im {_SEKTOR[nr]} Sektor, da verlierst du im Schnitt {_sek(v)} auf deine eigene Bestmarke.",
                          f"The biggest potential is in sector {nr}, you lose {_sek(v)} on average there compared to your own best."))
        if a["ideal"] and a["bestzeit"] and a["bestzeit"] - a["ideal"] > 200:
            luft.append(L(f"Mit deinen besten Sektoren zusammen wäre eine {_zeit(a['ideal'])} drin.",
                          f"With your best sectors together a {_zeit(a['ideal'])} is possible."))
        if a["spanne"] is not None and a["spanne"] >= 1.2:
            luft.append(L(f"Die Runden haben um {_sek(a['spanne'])} geschwankt, gleichmäßiger fahren bringt hier viel.",
                          f"The laps varied by {_sek(a['spanne'])}, being more consistent would gain a lot."))
        if a["trend"] is not None and a["trend"] > 0.12:
            luft.append(L("Gegen Ende bist du langsamer geworden, da können wir mit den Reifen schonender umgehen.",
                          "You got slower towards the end, we can look after the tyres better there."))
        if a["ungueltig"] >= 2:
            luft.append(L(f"{a['ungueltig']} Runden waren wegen Track Limits ungültig, da müssen wir drauf achten.",
                          f"{a['ungueltig']} laps were invalid for track limits, we need to watch that."))
        if a["strafen"]:
            luft.append(L(f"{'Die Strafe' if a['strafen'] == 1 else 'Die Strafen'} hat uns Zeit gekostet.",
                          f"The {'penalty' if a['strafen'] == 1 else 'penalties'} cost us time."))
        teile += lob[:3]
        if luft:
            teile.append(L("Wo noch was geht:", "Where there's more to find:") + " " + " ".join(luft[:2]))
        teile.append(L("Danke für die Arbeit heute. Ich bin jetzt ruhig, bis die nächste Session startet. "
                       "Wenn du was wissen willst, frag einfach.",
                       "Thanks for the work today. I'll stay quiet now until the next session starts. "
                       "If you want to know anything, just ask."))
        return " ".join(teile)

    def speichern(self):
        """Speichert die Session als Datei im Ordner 'rennen'."""
        if self.gespeichert or not self.runden:
            return None
        os.makedirs(RENNEN_ORDNER, exist_ok=True)
        zeitstempel = time.strftime("%Y-%m-%d_%H-%M", time.localtime(self.beginn))
        name = f"{zeitstempel}_{self.strecke or 'strecke'}_{SESSION_NAMEN.get(self.session, 'session')}.json"
        pfad = os.path.join(RENNEN_ORDNER, name)
        with open(pfad, "w", encoding="utf-8") as datei:
            daten = self.zusammenfassung()
            if self.telemetrie:
                daten["telemetrie"] = self.telemetrie
            if self.karte:
                daten["karte"] = self.karte
            json.dump(daten, datei, ensure_ascii=False, separators=(",", ":"))
        self.gespeichert = True
        return pfad


# ---------------------------------------------------------------------------
# Boxenstopp: wie viel Zeit kostet er, und wo kommst du wieder raus?
# ---------------------------------------------------------------------------
def karte_von(acc):
    """Der Streckenumriss, wie ihn die Live-Karte zeichnet (oder None, wenn noch zu wenig da ist)."""
    try:
        punkte = acc.streckenbild
        if len(punkte) <= 40:
            return None
        return [[round(punkte[f][0], 1), round(punkte[f][1], 1)] for f in sorted(punkte)]
    except Exception:
        return None


def boxenverlust(acc):
    """Geschätzter Zeitverlust durch einen Boxenstopp in Sekunden.
    Gemessen an allen Autos: Zeit von Boxeneinfahrt bis -ausfahrt, minus etwa 8 Sekunden,
    die man für das gleiche Stück auf der Strecke auch gebraucht hätte."""
    zeiten = sorted(acc.boxengassen_zeiten)
    if len(zeiten) >= 2:
        mitte = zeiten[len(zeiten) // 2]
        return max(15.0, min(90.0, mitte - 8.0))
    return 30.0


def wiedereinstieg(acc, verlust):
    """Wenn du jetzt an die Box fährst: Wo kommst du ungefähr wieder raus?
    Gibt (neuer_platz, (auto_vorne, sekunden) oder None, (auto_hinten, sekunden) oder None) zurück."""
    ich = acc.ich()
    liste = acc.rangliste()
    if ich is None or ich not in liste:
        return None
    mein_platz = liste.index(ich) + 1
    hinter_mir = []
    for auto in liste[mein_platz:]:
        if auto.ort in (2, 3, 4):
            continue                           # ist selbst gerade in der Box
        art, wert = acc.abstand_zu(auto)
        if art == "sek" and wert is not None and wert < 0:
            hinter_mir.append((auto, -wert))
    vorbei = [(auto, sek) for auto, sek in hinter_mir if sek < verlust]
    bleiben = [(auto, sek) for auto, sek in hinter_mir if sek >= verlust]
    neuer_platz = mein_platz + len(vorbei)
    if vorbei:
        vorne = (vorbei[-1][0], verlust - vorbei[-1][1])
    elif mein_platz > 1:                           # niemand kommt vorbei: Vordermann bleibt vorne
        art, wert = acc.abstand_zu(liste[mein_platz - 2])
        vorne = (liste[mein_platz - 2], wert + verlust) if art == "sek" and wert is not None else None
    else:
        vorne = None
    hinten = (bleiben[0][0], bleiben[0][1] - verlust) if bleiben else None
    return neuer_platz, vorne, hinten
