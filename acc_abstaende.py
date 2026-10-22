# acc_abstaende.py
# Schritt 2 des ACC-Renningenieurs:
# Verbindet sich mit der Broadcasting-Schnittstelle von ACC und berechnet
# die Abstände zum Vordermann und Hintermann in Sekunden.
#
# Vorher einmalig nötig: broadcasting.json in
#   Dokumente\Assetto Corsa Competizione\Config
# anpassen (siehe Anleitung im Chat) und ACC neu starten.
#
# Starten mit:  py -3.13 acc_abstaende.py
# Beenden mit:  Strg + C

import bisect   # schnelles Suchen in sortierten Listen
import os       # Fenster leeren
import socket   # Netzwerkverbindung (UDP) zu ACC
import struct   # Bytes in Zahlen umwandeln und umgekehrt
import time     # Zeitmessung


# ---------------------------------------------------------------------------
# Einstellungen: müssen zu deiner broadcasting.json passen
# ---------------------------------------------------------------------------
ACC_ADRESSE = ("127.0.0.1", 9000)   # 127.0.0.1 = dieser PC, 9000 = Port
VERBINDUNGS_PASSWORT = "asd"
UPDATE_INTERVALL_MS = 200           # ACC schickt alle 200 ms neue Daten

# Rennphasen aus der Zeitnahme
PHASE_FORMATIONSRUNDE, PHASE_VOR_START, PHASE_LAEUFT, PHASE_VORBEI, PHASE_NACH_SESSION = 3, 4, 5, 6, 7

SESSION_NAMEN = {
    0: "Training", 4: "Qualifying", 9: "Superpole", 10: "Rennen",
    11: "Hotlap", 12: "Hotstint", 13: "Hotlap Superpole", 14: "Replay",
}


# ---------------------------------------------------------------------------
# 1) Leser: holt der Reihe nach Werte aus einem empfangenen Datenpaket
# ACC schickt nur Bytes. Wir wissen aus der Dokumentation, in welcher
# Reihenfolge welche Werte kommen, und lesen sie nacheinander aus.
# ---------------------------------------------------------------------------
class Leser:
    def __init__(self, daten):
        self.daten = daten
        self.pos = 0   # wie weit wir schon gelesen haben

    def _lies(self, format):
        wert = struct.unpack_from("<" + format, self.daten, self.pos)[0]
        self.pos += struct.calcsize("<" + format)
        return wert

    def u8(self):  return self._lies("B")   # Zahl 0 bis 255
    def u16(self): return self._lies("H")   # Zahl 0 bis 65535
    def i32(self): return self._lies("i")   # große ganze Zahl
    def f32(self): return self._lies("f")   # Kommazahl

    def text(self):
        laenge = self.u16()
        roh = self.daten[self.pos:self.pos + laenge]
        self.pos += laenge
        return roh.decode("utf-8", errors="replace")

    def runde_voll(self):
        """Liest eine Runden-Info. Gibt (Zeit, [Sektorzeiten], ungültig) zurück, Zeiten in
        Millisekunden, None für Werte, die es (noch) nicht gibt."""
        gueltig = lambda wert: None if wert <= 0 or wert == 2147483647 else wert
        zeit = self.i32()
        self.u16()                      # Auto-Nummer intern
        self.u16()                      # Fahrer-Nummer intern
        sektoren = [gueltig(self.i32()) for _ in range(self.u8())]
        ungueltig = self.u8()
        fuer_bestzeit, outlap, inlap = self.u8(), self.u8(), self.u8()
        # Track Limits: ACC setzt manchmal nur "nicht gültig für die Bestzeit". Aus- und Einfahrtsrunden zählen nicht als ungültig.
        ungueltig = ungueltig or (not fuer_bestzeit and not outlap and not inlap)
        return gueltig(zeit), sektoren, bool(ungueltig)

    def runde_mit_sektoren(self):
        zeit, sektoren, _ = self.runde_voll()
        return zeit, sektoren

    def runde(self):
        """Liest eine Runden-Info und gibt nur die Zeit in Millisekunden zurück."""
        return self.runde_mit_sektoren()[0]


def text_als_bytes(text):
    """Text so verpacken, wie ACC ihn erwartet: erst Länge, dann Zeichen."""
    roh = text.encode("utf-8")
    return struct.pack("<H", len(roh)) + roh


# ---------------------------------------------------------------------------
# 2) Ein Auto im Feld
# Jedes Auto merkt sich, zu welchem Zeitpunkt es an welcher Stelle war.
# Daraus berechnen wir später echte Zeitabstände.
# ---------------------------------------------------------------------------
KARTEN_PUNKTE = 400      # so fein wird die Streckenform gespeichert


class Auto:
    def __init__(self, index):
        self.index = index
        self.nummer = None
        self.fahrer = "?"
        self.position = 0
        self.kmh = 0
        self.letzte_runde = None
        self.beste_runde = None
        self.ort = 1                # 1 Strecke, 2 Boxengasse, 3 Boxeneinfahrt, 4 Boxenausfahrt
        self.letzte_sektoren = []   # Sektorzeiten der letzten Runde (ms)
        self.beste_sektoren = []    # Sektorzeiten der besten Runde (ms)
        self.boxenstopps = 0        # wie oft in der Boxengasse
        self.box_seit = None        # seit wann in der Boxengasse (Zeitpunkt)
        self.runden_historie = []   # alle gefahrenen Runden: {"runde", "zeit", "sektoren", "gueltig"}
        self.x = self.y = None      # Position auf der Karte
        self.modell = None          # Automodell (Nummer von ACC)
        self.platz = None           # Platz in der Rangliste (wird von rangliste() gesetzt)
        self.acc_runden = 0         # fertige Runden laut ACC
        self.runden_zaehler = None
        self.spline = 0.0           # 0.0 = Start/Ziel, 0.5 = halbe Runde
        self.abweichung_seit = None
        # Verlauf: strecken[i] = gefahrene Runden (z. B. 12.37), zeiten[i] = Zeitpunkt
        self.strecken = []
        self.zeiten = []

    def gefahrene_strecke(self):
        """Runden + Anteil der aktuellen Runde, z. B. 12.37"""
        return self.runden_zaehler + self.spline

    def neue_position(self, spline, runden, jetzt):
        if self.runden_zaehler is None:
            self.runden_zaehler = runden
        elif spline < self.spline - 0.5:      # über Start/Ziel gefahren
            self.runden_zaehler += 1
        elif spline > self.spline + 0.5:      # rückwärts über die Linie
            self.runden_zaehler -= 1
        self.spline = spline

        # Abgleich mit der Rundenzahl von ACC: Beim Rennstart stehen Autos
        # hinter der Linie, dann zählt unser Zähler eine Runde zu viel.
        # Weicht er mitten auf der Strecke länger als 3 s ab, übernehmen wir ACCs Wert.
        if runden != self.runden_zaehler and 0.1 < spline < 0.9:
            if self.abweichung_seit is None:
                self.abweichung_seit = jetzt
            elif jetzt - self.abweichung_seit > 3:
                self.runden_zaehler = runden
                self.abweichung_seit = None
        else:
            self.abweichung_seit = None

        strecke = self.gefahrene_strecke()
        if self.strecken and strecke < self.strecken[-1] - 0.5:
            # Auto wurde zurückgesetzt (z. B. zurück in die Box): Verlauf neu
            self.strecken.clear()
            self.zeiten.clear()
        if not self.strecken or strecke > self.strecken[-1]:
            self.strecken.append(strecke)
            self.zeiten.append(jetzt)
            if len(self.strecken) > 4000:     # alten Verlauf wegwerfen
                del self.strecken[:1000]
                del self.zeiten[:1000]

    def zeitpunkt_bei(self, strecke):
        """Wann war dieses Auto an dieser Stelle? None, wenn unbekannt."""
        if len(self.strecken) < 2:
            return None
        if strecke < self.strecken[0] or strecke > self.strecken[-1]:
            return None
        i = bisect.bisect_left(self.strecken, strecke)
        if i == 0:
            return self.zeiten[0]
        s0, s1 = self.strecken[i - 1], self.strecken[i]
        t0, t1 = self.zeiten[i - 1], self.zeiten[i]
        if s1 == s0:
            return t1
        # zwischen zwei Messpunkten genau ausrechnen
        return t0 + (t1 - t0) * (strecke - s0) / (s1 - s0)


# ---------------------------------------------------------------------------
# 3) Die Verbindung zu ACC
# ---------------------------------------------------------------------------
class AccVerbindung:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(0.1)
        self.verbindungs_id = None
        self.fehler = ""
        self.autos = {}
        self.mein_index = None
        self.session_typ = None
        self.streckenlaenge_m = None
        self.letzte_nachricht = 0.0
        self.letzter_versuch = 0.0
        self.letzte_listen_anfrage = 0.0
        self.phase = 0                       # Rennphase, siehe PHASEN
        self.box_ereignisse = []             # (zeit, auto-index, "rein"/"raus", dauer) für Ansagen
        self.streckenbild = {}               # Fach (0..KARTEN_PUNKTE) -> [x, y, Anzahl]: die Streckenform
        self.streckenname = ""
        self.boxengassen_zeiten = []         # gemessene Zeiten von Einfahrt bis Ausfahrt (s)
        # für die Diagnose
        self.auto_pakete = 0          # Auto-Updates seit der letzten Messung
        self.auto_pakete_pro_s = 0
        self.messung_start = time.monotonic()
        self.mein_letztes_update = None

    # --- Senden --------------------------------------------------------------
    def _senden(self, daten):
        try:
            self.sock.sendto(daten, ACC_ADRESSE)
        except OSError:
            pass

    def anmelden(self):
        daten = (struct.pack("<BB", 1, 4)                 # 1 = anmelden, Version 4
                 + text_als_bytes("PitVoice AI")
                 + text_als_bytes(VERBINDUNGS_PASSWORT)
                 + struct.pack("<i", UPDATE_INTERVALL_MS)
                 + text_als_bytes(""))                    # kein Befehls-Passwort
        self._senden(daten)
        self.letzter_versuch = time.monotonic()

    def abmelden(self):
        if self.verbindungs_id is not None:
            self._senden(struct.pack("<Bi", 9, self.verbindungs_id))

    def fahrerliste_anfordern(self):
        if self.verbindungs_id is not None:
            self._senden(struct.pack("<Bi", 10, self.verbindungs_id))
            self.letzte_listen_anfrage = time.monotonic()

    def streckendaten_anfordern(self):
        if self.verbindungs_id is not None:
            self._senden(struct.pack("<Bi", 11, self.verbindungs_id))

    # --- Verbindung am Leben halten -----------------------------------------
    def pflegen(self):
        jetzt = time.monotonic()
        keine_daten = jetzt - self.letzte_nachricht > 5
        if (self.verbindungs_id is None or keine_daten) and jetzt - self.letzter_versuch > 2:
            self.verbindungs_id = None
            self.anmelden()
        # Fehlen bei manchen Autos noch Name oder Startnummer? Dann die Liste erneut anfordern.
        elif (self.verbindungs_id is not None and jetzt - self.letzte_listen_anfrage > 10
              and any(a.fahrer == "?" or a.nummer is None for a in self.autos.values())):
            self.fahrerliste_anfordern()

    # --- Empfangen -----------------------------------------------------------
    def empfangen(self):
        """Pakete verarbeiten, aber höchstens 0,1 Sekunden lang.
        Danach geht es zurück zur Hauptschleife, damit die Anzeige
        regelmäßig aktualisiert wird, auch wenn ACC pausenlos Daten schickt."""
        ende = time.monotonic() + 0.1
        while True:
            rest = ende - time.monotonic()
            if rest <= 0:
                return
            self.sock.settimeout(rest)
            try:
                daten, _ = self.sock.recvfrom(65535)
            except socket.timeout:
                return
            except ConnectionResetError:
                # Windows meldet das, wenn ACC (noch) nicht zuhört
                return
            self.letzte_nachricht = time.monotonic()
            try:
                self._verarbeiten(daten)
            except struct.error:
                pass   # unvollständiges Paket ignorieren

    def _verarbeiten(self, daten):
        leser = Leser(daten)
        typ = leser.u8()
        jetzt = time.monotonic()

        if typ == 1:      # Antwort auf die Anmeldung
            vid = leser.i32()
            erfolg = leser.u8()
            leser.u8()
            fehler = leser.text()
            if erfolg:
                self.verbindungs_id = vid
                self.fehler = ""
                self.fahrerliste_anfordern()
                self.streckendaten_anfordern()
            else:
                self.fehler = fehler or "Anmeldung abgelehnt"

        elif typ == 2:    # allgemeine Session-Infos
            leser.u16(); leser.u16()
            self.session_typ = leser.u8()
            self.phase = leser.u8()
            leser.f32(); leser.f32()
            self.mein_index = leser.i32()    # das Auto, das gerade im Fokus ist (du)

        elif typ == 3:    # Live-Daten eines Autos
            index = leser.u16()
            leser.u16(); leser.u8(); leser.u8()
            welt_x, welt_y = leser.f32(), leser.f32()
            leser.f32()
            ort = leser.u8()
            kmh = leser.u16()
            position = leser.u16()
            leser.u16(); leser.u16()
            spline = leser.f32()
            runden = leser.u16()
            leser.i32()
            beste, beste_sektoren = leser.runde_mit_sektoren()
            letzte, letzte_sektoren, letzte_ungueltig = leser.runde_voll()
            leser.runde()

            auto = self.autos.get(index)
            if auto is None:
                auto = Auto(index)
                self.autos[index] = auto
                if jetzt - self.letzte_listen_anfrage > 2:
                    self.fahrerliste_anfordern()   # neues Auto: Namen holen
            # Boxengasse: rein und raus merken (für Gegner-Stopps und den Zeitverlust beim Stopp)
            in_box = ort in (2, 3, 4)
            war_in_box = auto.box_seit is not None
            if in_box and not war_in_box and auto.runden_zaehler is not None:
                auto.box_seit = jetzt
                auto.boxenstopps += 1
                self.box_ereignisse.append((jetzt, index, "rein", None))
            elif not in_box and war_in_box:
                dauer = jetzt - auto.box_seit
                auto.box_seit = None
                self.box_ereignisse.append((jetzt, index, "raus", dauer))
                if 8 < dauer < 180:
                    self.boxengassen_zeiten.append(dauer)
                    del self.boxengassen_zeiten[:-20]
            del self.box_ereignisse[:-50]
            auto.ort = ort
            if letzte_sektoren:
                auto.letzte_sektoren = letzte_sektoren
            if beste_sektoren:
                auto.beste_sektoren = beste_sektoren
            self.auto_pakete += 1
            if index == self.mein_index:
                self.mein_letztes_update = jetzt
            # Rundenverlauf jedes Autos (für die Live-Seite)
            if letzte and runden != auto.acc_runden and runden > 0:
                if not auto.runden_historie or auto.runden_historie[-1]["runde"] != runden:
                    auto.runden_historie.append({"runde": runden, "zeit": letzte,
                                                 "sektoren": list(letzte_sektoren),
                                                 "gueltig": not letzte_ungueltig,
                                                 "box": ort in (2, 3, 4)})
                    del auto.runden_historie[:-60]
            elif letzte and runden > 0 and auto.runden_historie and auto.runden_historie[-1]["runde"] == runden:
                # Die Zeitnahme schickt die neue Runde oft erst ein paar Pakete nach dem Rundenzähler:
                # dann den Eintrag mit den richtigen Werten (Zeit, Sektoren, Track Limits) nachziehen.
                eintrag = auto.runden_historie[-1]
                if eintrag["zeit"] != letzte or eintrag["gueltig"] == bool(letzte_ungueltig) \
                        or (letzte_sektoren and eintrag["sektoren"] != list(letzte_sektoren)):
                    eintrag["zeit"] = letzte
                    if letzte_sektoren:
                        eintrag["sektoren"] = list(letzte_sektoren)
                    eintrag["gueltig"] = not letzte_ungueltig
            auto.acc_runden = runden
            # Karte: Position merken und die Streckenform aus allen fahrenden Autos lernen
            if welt_x or welt_y:
                auto.x, auto.y = welt_x, welt_y
                if ort == 1 and kmh > 30:
                    fach = int(spline * KARTEN_PUNKTE) % KARTEN_PUNKTE
                    punkt = self.streckenbild.get(fach)
                    if punkt is None:
                        self.streckenbild[fach] = [welt_x, welt_y, 1]
                    elif punkt[2] < 30:            # Mittelwert aus den ersten 30 Durchfahrten
                        punkt[0] += (welt_x - punkt[0]) / (punkt[2] + 1)
                        punkt[1] += (welt_y - punkt[1]) / (punkt[2] + 1)
                        punkt[2] += 1
            auto.kmh = kmh
            auto.position = position
            auto.beste_runde = beste
            auto.letzte_runde = letzte
            auto.neue_position(spline, runden, jetzt)

        elif typ == 4:    # Liste aller Autos
            leser.i32()
            anzahl = leser.u16()
            indizes = {leser.u16() for _ in range(anzahl)}
            for index in list(self.autos):
                if index not in indizes:
                    del self.autos[index]          # Auto hat die Session verlassen
            for index in indizes:
                self.autos.setdefault(index, Auto(index))

        elif typ == 5:    # Streckendaten
            leser.i32()
            name = leser.text()
            if name != self.streckenname:
                self.streckenname = name
                self.streckenbild = {}             # neue Strecke: Karte neu lernen
            leser.i32()
            self.streckenlaenge_m = leser.i32()

        elif typ == 6:    # Infos zu einem Auto (Startnummer, Fahrer)
            index = leser.u16()
            modell = leser.u8()               # Automodell (Nummer, siehe acc_renningenieur.MARKEN)
            leser.text()                      # Teamname
            nummer = leser.i32()
            leser.u8()
            aktueller_fahrer = leser.u8()
            leser.u16()
            fahrer = []
            for _ in range(leser.u8()):
                vorname = leser.text()
                nachname = leser.text()
                leser.text(); leser.u8(); leser.u16()
                fahrer.append(f"{vorname} {nachname}".strip())
            auto = self.autos.setdefault(index, Auto(index))
            auto.nummer = nummer
            auto.modell = modell
            if fahrer:
                auto.fahrer = fahrer[min(aktueller_fahrer, len(fahrer) - 1)]

    # --- Auswertung ----------------------------------------------------------
    def ich(self):
        return self.autos.get(self.mein_index)

    def auto_auf_position(self, position):
        for auto in self.autos.values():
            if auto.position == position:
                return auto
        return None

    def live_reihenfolge(self):
        """Alle Autos, sortiert nach gefahrener Strecke: wer am weitesten ist, führt.
        Das ist sofort aktuell, auch direkt nach einem Überholmanöver.
        (ACCs eigene Platzierung hängt hinterher, sie wird nur an Messpunkten aktualisiert.)"""
        autos = [a for a in self.autos.values() if a.runden_zaehler is not None]
        autos.sort(key=lambda a: a.gefahrene_strecke(), reverse=True)
        return autos

    def ist_rennen(self):
        return self.session_typ == 10

    def rangliste(self):
        """Alle Autos in Platzierungs-Reihenfolge (Index 0 = P1).
        Im Rennen nach gefahrener Strecke, sonst nach ACCs Platzierung."""
        if self.ist_rennen():
            autos = self.live_reihenfolge()
        else:
            autos = [a for a in self.autos.values() if a.position > 0]
            autos.sort(key=lambda a: a.position)
        for platz, auto in enumerate(autos, start=1):
            auto.platz = platz                 # damit der Ingenieur "der Ferrari auf Platz 5" sagen kann
        return autos

    def auto_auf_platz(self, platz):
        """Das Auto auf Platz 'platz' (1 = Führender), oder None."""
        liste = self.rangliste()
        if 1 <= platz <= len(liste):
            return liste[platz - 1]
        return None

    def mein_platz(self):
        ich = self.ich()
        liste = self.rangliste()
        if ich in liste:
            return liste.index(ich) + 1
        return None

    def abstand_zu(self, anderes):
        """Abstand von dir zu einem beliebigen Auto.
        Gibt (art, wert) zurück:
          ("sek", 4.2)    -> das Auto ist 4,2 s VOR dir
          ("sek", -1.5)   -> das Auto ist 1,5 s HINTER dir
          ("runden", 1)   -> das Auto ist 1 Runde vor dir
          ("runden", -2)  -> du hast das Auto 2-mal überrundet
          (None, None)    -> noch unbekannt"""
        ich = self.ich()
        if ich is None or anderes is None or anderes is ich:
            return None, None
        if self.ist_rennen():
            if ich.runden_zaehler is None or anderes.runden_zaehler is None:
                return None, None
            unterschied = anderes.gefahrene_strecke() - ich.gefahrene_strecke()
            if abs(unterschied) >= 1:                 # mindestens eine Runde
                return "runden", int(unterschied)
            if unterschied >= 0:
                return "sek", self.abstand(anderes, ich)
            sekunden = self.abstand(ich, anderes)
            return "sek", (-sekunden if sekunden is not None else None)
        # Training/Quali: Unterschied der besten Runden
        if ich.beste_runde and anderes.beste_runde:
            return "sek", (ich.beste_runde - anderes.beste_runde) / 1000
        return None, None

    def nachbarn(self):
        """Gibt (meinen Platz, Auto vorne, Auto hinten) zurück."""
        platz = self.mein_platz()
        if platz is None:
            return None, None, None
        return platz, self.auto_auf_platz(platz - 1) if platz > 1 else None, self.auto_auf_platz(platz + 1)

    def abstand(self, vorne, hinten):
        """Sekunden, die 'hinten' braucht, um dahin zu kommen, wo 'vorne' ist."""
        if vorne is None or hinten is None:
            return None
        if vorne.runden_zaehler is None or hinten.runden_zaehler is None:
            return None
        # Genau: Wann war 'vorne' an der Stelle, an der 'hinten' jetzt ist?
        if hinten.zeiten:
            zeitpunkt = vorne.zeitpunkt_bei(hinten.gefahrene_strecke())
            if zeitpunkt is not None:
                return hinten.zeiten[-1] - zeitpunkt
        # Grob (am Anfang, solange noch kein Verlauf da ist): Strecke / Tempo
        if self.streckenlaenge_m and hinten.kmh > 20:
            meter = (vorne.gefahrene_strecke() - hinten.gefahrene_strecke()) * self.streckenlaenge_m
            return meter / (hinten.kmh / 3.6)
        return None


# ---------------------------------------------------------------------------
# 4) Anzeige
# ---------------------------------------------------------------------------
def zeit_text(ms):
    if ms is None:
        return "-"
    minuten = ms // 60000
    sekunden = (ms % 60000) / 1000
    return f"{minuten}:{sekunden:06.3f}"

def name_text(auto):
    if auto is None:
        return "-"
    nummer = f"#{auto.nummer} " if auto.nummer is not None else ""
    return f"{nummer}{auto.fahrer}"

def abstand_text(art, wert):
    """Macht aus dem Ergebnis von abstand_zu() einen kurzen Text."""
    if art is None or wert is None:
        return "..."
    if art == "runden":
        runden = abs(wert)
        wort = "Runde" if runden == 1 else "Runden"
        return f"+{runden} {wort}" if wert > 0 else f"-{runden} {wort}"
    return f"{wert:+.1f} s"      # + vor dir, - hinter dir


def anzeigen(acc):
    # Cursor nach oben links setzen und alles darunter löschen.
    # Das ist viel schneller und flackert weniger als "cls".
    print("\033[H\033[J", end="")
    if acc.verbindungs_id is None:
        print("Verbinde mit ACC (Port 9000) ...")
        if acc.fehler:
            print(f"ACC meldet: {acc.fehler}")
        print("Läuft ACC? Ist die broadcasting.json angepasst?")
        return

    ich = acc.ich()
    mein_platz = acc.mein_platz()
    if ich is None or mein_platz is None:
        print("Verbunden. Warte auf Daten - fahr auf die Strecke.")
        return

    session = SESSION_NAMEN.get(acc.session_typ, f"Typ {acc.session_typ}")
    print(f"{session}  |  Du: P{mein_platz} von {len(acc.rangliste())}"
          f"  |  Letzte {zeit_text(ich.letzte_runde)}  Beste {zeit_text(ich.beste_runde)}")
    print("=" * 66)
    print(f"{'P':>3}  {'Nr':>4}  {'Fahrer':<22} {'Abstand':>11}  {'Letzte':>9}  Box")
    print("-" * 66)
    for platz, auto in enumerate(acc.rangliste(), start=1):
        if auto is ich:
            abstand = "--- DU ---"
            markierung = ">"
        else:
            abstand = abstand_text(*acc.abstand_zu(auto))
            markierung = " "
        nummer = f"#{auto.nummer}" if auto.nummer is not None else ""
        box = "BOX" if auto.ort in (2, 3, 4) else ""
        print(f"{markierung}{platz:>2}  {nummer:>4}  {auto.fahrer[:22]:<22} "
              f"{abstand:>11}  {zeit_text(auto.letzte_runde):>9}  {box}")
    print("-" * 66)
    print("Abstand: + = vor dir, - = hinter dir")
    alter = "-"
    if acc.mein_letztes_update is not None:
        alter = f"{time.monotonic() - acc.mein_letztes_update:.1f} s"
    print(f"Diagnose: Session-Typ {acc.session_typ} | "
          f"{acc.auto_pakete_pro_s} Auto-Updates/s | dein Auto zuletzt vor {alter}")
    if not acc.ist_rennen():
        print("Training/Quali: Abstand = Unterschied der besten Runden")


# ---------------------------------------------------------------------------
# 5) Hauptprogramm
# ---------------------------------------------------------------------------
def main():
    acc = AccVerbindung()
    letzte_anzeige = 0.0
    os.system("")   # schaltet in der Windows-Konsole die schnelle Anzeige frei
    print("Starte ... (Beenden mit Strg + C)")
    try:
        while True:
            acc.pflegen()
            acc.empfangen()
            jetzt = time.monotonic()
            if jetzt - acc.messung_start >= 1:          # Pakete pro Sekunde messen
                acc.auto_pakete_pro_s = acc.auto_pakete
                acc.auto_pakete = 0
                acc.messung_start = jetzt
            if jetzt - letzte_anzeige >= 0.25:          # 4x pro Sekunde anzeigen
                anzeigen(acc)
                letzte_anzeige = time.monotonic()
    except KeyboardInterrupt:
        acc.abmelden()
        print("\nBeendet.")


# Nur ausführen, wenn diese Datei direkt gestartet wird.
# So können wir sie später im Renningenieur einfach mitbenutzen.
if __name__ == "__main__":
    main()
