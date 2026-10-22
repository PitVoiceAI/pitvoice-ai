# acc_sprit.py
# Schritt 3 des ACC-Renningenieurs: Spritrechnung und Boxenfenster.
#
# Misst deinen echten Verbrauch pro Runde und rechnet aus:
#   - wie viele Runden der Tank noch reicht
#   - wie viel Sprit du bis ins Ziel brauchst
#   - ob und wie viel du nachtanken musst
#   - in welchen Runden du an die Box kannst (Boxenfenster)
#
# Starten mit:  py -3.13 acc_sprit.py
# Beenden mit:  Strg + C

import math
import os
import time

# ---------------------------------------------------------------------------
# Einstellungen
# ---------------------------------------------------------------------------
RESERVE_RUNDEN = 0.5     # so viel Sprit (in Runden) soll im Ziel übrig sein
RUNDEN_FUER_SCHNITT = 5  # aus wie vielen der letzten Runden der Schnitt kommt


# ---------------------------------------------------------------------------
# 1) Verbrauch messen
# Am Ende jeder Runde vergleichen wir den Tank mit dem Tank am Rundenstart.
# Runden mit Boxenbesuch oder Nachtanken zählen nicht, die würden den
# Schnitt verfälschen.
# ---------------------------------------------------------------------------
class VerbrauchsMesser:
    def __init__(self):
        self.verbrauch_liste = []      # Liter pro gültiger Runde
        self.zeiten_liste = []         # Rundenzeiten in Sekunden
        self.letzte_runden_nr = None
        self.tank_bei_rundenstart = None
        self.runde_ungueltig = True    # die erste Runde sehen wir nicht komplett
        self.letzter_tank = None

    def aktualisieren(self, tank, runden_fertig, in_boxengasse, letzte_rundenzeit_ms):
        # Neue Session (Rundenzahl springt zurück): alles neu
        if self.letzte_runden_nr is not None and runden_fertig < self.letzte_runden_nr:
            self.__init__()

        # Nachgetankt oder in der Boxengasse: diese Runde zählt nicht
        if self.letzter_tank is not None and tank > self.letzter_tank + 0.3:
            self.runde_ungueltig = True
        if in_boxengasse:
            self.runde_ungueltig = True
        self.letzter_tank = tank

        if self.letzte_runden_nr is None:
            self.letzte_runden_nr = runden_fertig
            return

        if runden_fertig > self.letzte_runden_nr:          # Runde beendet!
            genau_eine = runden_fertig == self.letzte_runden_nr + 1
            if not self.runde_ungueltig and genau_eine and self.tank_bei_rundenstart is not None:
                verbrauch = self.tank_bei_rundenstart - tank
                if 0.1 < verbrauch < 20:                    # Unsinn aussortieren
                    self.verbrauch_liste.append(verbrauch)
                    self.verbrauch_liste = self.verbrauch_liste[-RUNDEN_FUER_SCHNITT:]
                    if letzte_rundenzeit_ms > 0:
                        self.zeiten_liste.append(letzte_rundenzeit_ms / 1000)
                        self.zeiten_liste = self.zeiten_liste[-RUNDEN_FUER_SCHNITT:]
            # neue Runde beginnt
            self.tank_bei_rundenstart = tank
            self.runde_ungueltig = bool(in_boxengasse)
            self.letzte_runden_nr = runden_fertig

    def verbrauch_schnitt(self):
        if not self.verbrauch_liste:
            return None
        return sum(self.verbrauch_liste) / len(self.verbrauch_liste)

    def rundenzeit_schnitt(self):
        if not self.zeiten_liste:
            return None
        return sum(self.zeiten_liste) / len(self.zeiten_liste)


# ---------------------------------------------------------------------------
# 2) Strategie rechnen
# Reine Rechnung ohne ACC, damit man sie leicht prüfen kann.
# ---------------------------------------------------------------------------
def restrunden_berechnen(runden_fertig, runden_anteil, runden_gesamt,
                         session_rest_ms, rundenzeit_s, extrarunde):
    """Wie viele Runden musst du noch fahren (inklusive der aktuellen)?"""
    if runden_gesamt > 0:
        # Rennen über eine feste Rundenzahl
        return max(0.0, runden_gesamt - runden_fertig - runden_anteil)
    if session_rest_ms > 0 and rundenzeit_s:
        # Rennen nach Zeit: Wenn die Uhr abläuft, fährst du die Runde noch zu Ende
        runden_bis_zeitende = (session_rest_ms / 1000) / rundenzeit_s
        rest = math.ceil(runden_anteil + runden_bis_zeitende) - runden_anteil
        if extrarunde:
            rest += 1
        return rest
    return None


def strategie_berechnen(tank, tank_max, verbrauch, restrunden, runden_fertig, runden_anteil):
    """Gibt ein Wörterbuch mit allen Ergebnissen zurück."""
    e = {}
    reserve = RESERVE_RUNDEN * verbrauch
    e["reicht_runden"] = tank / verbrauch
    e["benoetigt"] = restrunden * verbrauch + reserve
    e["nachtanken"] = e["benoetigt"] - tank
    e["aktuelle_runde"] = runden_fertig + 1

    if e["nachtanken"] <= 0:
        e["stopps"] = 0
        e["ueberschuss"] = -e["nachtanken"]
        return e

    # Pro Stopp kann man höchstens so viel tanken, wie in den Tank passt
    platz_pro_stopp = max(tank_max - reserve, 1)
    e["stopps"] = math.ceil(e["nachtanken"] / platz_pro_stopp)
    e["menge_pro_stopp"] = math.ceil(e["nachtanken"] / e["stopps"])

    # Boxenfenster (nur bei einem Stopp sinnvoll):
    # j = am Ende der wievielten Runde ab jetzt du reinkommst (1 = diese Runde)
    # Spätestens: bevor der Tank leer ist (mit kleiner Reserve)
    j_spaet = math.floor(tank / verbrauch + runden_anteil - RESERVE_RUNDEN)
    # Frühestens: wenn die nötige Menge in den Tank passt
    j_frueh = math.ceil(runden_anteil + (e["nachtanken"] - tank_max + tank) / verbrauch)
    j_frueh = max(1, j_frueh)
    e["fenster_von"] = runden_fertig + j_frueh
    e["fenster_bis"] = runden_fertig + j_spaet
    return e


# ---------------------------------------------------------------------------
# 3) Anzeige
# ---------------------------------------------------------------------------
def zeit_text(sekunden):
    if not sekunden:
        return "-"
    return f"{int(sekunden // 60)}:{sekunden % 60:04.1f}"


def anzeigen(physik, grafik, statisch, messer):
    from acc_speicher import STATUS_AUS, STATUS_PAUSE
    print("\033[H\033[J", end="")

    if grafik.status == STATUS_AUS:
        print("Warte auf ACC ... fahr auf die Strecke.")
        return

    print("============== SPRIT & STRATEGIE ==============")
    print(f"{statisch.auto}  |  {statisch.strecke}")
    if statisch.verbrauchs_faktor == 0:
        print("\n!! Spritverbrauch ist in ACC ausgeschaltet, nichts zu rechnen.")
        return
    print("-----------------------------------------------")

    tank = physik.tank
    print(f"Tank:          {tank:5.1f} L  von {statisch.tank_max:.0f} L")

    # Verbrauch: eigene Messung, sonst ACCs Schätzung
    verbrauch = messer.verbrauch_schnitt()
    if verbrauch:
        quelle = f"Schnitt aus {len(messer.verbrauch_liste)} Runde(n)"
    elif grafik.sprit_pro_runde > 0:
        verbrauch = grafik.sprit_pro_runde
        quelle = "ACC-Schätzung, eigene Messung läuft"
    if not verbrauch:
        print("\nFahr eine komplette Runde ohne Box, dann wird gerechnet.")
        return
    print(f"Verbrauch:     {verbrauch:5.2f} L/Runde  ({quelle})")
    print(f"ACC schätzt:   {grafik.sprit_pro_runde:5.2f} L/Runde  "
          f"/ {grafik.sprit_runden_geschaetzt:.1f} Runden")

    rundenzeit = messer.rundenzeit_schnitt()
    if not rundenzeit and grafik.i_letzte_zeit > 0:
        rundenzeit = grafik.i_letzte_zeit / 1000
    print(f"Rundenzeit Ø:  {zeit_text(rundenzeit)}")

    restrunden = restrunden_berechnen(grafik.runden_fertig, grafik.runden_anteil,
                                      grafik.runden_gesamt, grafik.session_rest,
                                      rundenzeit, statisch.extrarunde)
    e = strategie_berechnen(tank, statisch.tank_max, verbrauch, restrunden or 0,
                            grafik.runden_fertig, grafik.runden_anteil)

    print(f"Reicht noch:   {e['reicht_runden']:5.1f} Runden")
    print("-----------------------------------------------")
    if restrunden is None:
        print("Renndauer unbekannt (noch keine Rundenzeit).")
        return
    if grafik.runden_gesamt > 0:
        art = f"Rennen über {grafik.runden_gesamt} Runden"
    else:
        sek = int(grafik.session_rest / 1000)
        art = f"nach Zeit, noch {sek // 60}:{sek % 60:02d} min"
    print(f"Bis ins Ziel:  {restrunden:5.1f} Runden  ({art})")
    print(f"Sprit nötig:   {e['benoetigt']:5.1f} L  (inkl. {RESERVE_RUNDEN} Runden Reserve)")
    print("===============================================")

    if e["stopps"] == 0:
        print(f"KEIN STOPP NÖTIG  -  {e['ueberschuss']:.1f} L Überschuss im Ziel")
    elif e["stopps"] == 1:
        print("BOXENSTOPP NÖTIG")
        print(f"Nachtanken:    {e['menge_pro_stopp']} L")
        if e["fenster_von"] <= e["fenster_bis"]:
            print(f"Boxenfenster:  Runde {e['fenster_von']} bis {e['fenster_bis']}"
                  f"  (du bist in Runde {e['aktuelle_runde']})")
            if e["aktuelle_runde"] > e["fenster_bis"]:
                print("!! SOFORT REIN, der Sprit wird knapp!")
        else:
            print("!! Sprit wird knapp, so bald wie möglich an die Box!")
    else:
        print(f"{e['stopps']} STOPPS NÖTIG  -  je ca. {e['menge_pro_stopp']} L")
        print(f"Erster Stopp spätestens in Runde {e['fenster_bis']}")

    if grafik.status == STATUS_PAUSE:
        print("\n(Spiel ist pausiert)")


# ---------------------------------------------------------------------------
# 4) Hauptprogramm
# ---------------------------------------------------------------------------
def main():
    from acc_speicher import AccSpeicher
    os.system("")          # schnelle Anzeige in der Windows-Konsole
    speicher = AccSpeicher()
    messer = VerbrauchsMesser()
    print("Starte ... (Beenden mit Strg + C)")
    try:
        while True:
            physik, grafik, statisch = speicher.lesen()
            if grafik.status != 0:
                messer.aktualisieren(physik.tank, grafik.runden_fertig,
                                     grafik.in_boxengasse or grafik.in_box,
                                     grafik.i_letzte_zeit)
            anzeigen(physik, grafik, statisch, messer)
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nBeendet.")


if __name__ == "__main__":
    main()
