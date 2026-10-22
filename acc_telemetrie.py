from acc_sprache import L
# acc_telemetrie.py
# Zeichnet jede Runde auf: Tempo, Gas, Bremse und Gang an 500 Stellen der Strecke.
# Damit kann der Ingenieur deine Runde mit deiner Bestrunde vergleichen:
#   - in welcher Kurve du Zeit verlierst
#   - ob du früher bremst, langsamer durch die Kurve fährst oder später aufs Gas gehst
# Die Kurven findet das Programm selbst (dort, wo du stark abbremst) und zählt sie
# in Fahrtrichtung durch: Kurve 1, Kurve 2 ... (das muss nicht die offizielle Nummer sein).
#
# Diese Datei startet man nicht selbst.

PUNKTE = 500                 # so fein wird eine Runde aufgezeichnet
MAX_RUNDEN = 60


class Aufzeichnung:
    def __init__(self):
        self.zuruecksetzen()

    def zuruecksetzen(self):
        self.runden = {}              # Rundennummer -> Spur
        self.beste_nr = None
        self.aktuell = None
        self.letzte_runden = None
        self.sitzung = None
        self.gestartet = False
        self.ungueltige_zeiten = set()   # Rundenzeiten, die nachträglich als ungültig erkannt wurden

    def _neue_runde(self, nummer):
        self.aktuell = {"nr": nummer, "tempo": [None] * PUNKTE, "gas": [None] * PUNKTE,
                        "bremse": [None] * PUNKTE, "gang": [None] * PUNKTE, "zeit": [None] * PUNKTE,
                        "gueltig": True, "box": False}
        self.gestartet = False

    def aufzeichnen(self, physik, grafik):
        """Wird ständig aufgerufen (etwa 50 Mal pro Sekunde)."""
        if grafik.status != 2:
            return
        sitzung = (grafik.session, grafik.session_index)
        runden = grafik.runden_fertig
        if sitzung != self.sitzung or (self.letzte_runden is not None and runden < self.letzte_runden):
            self.zuruecksetzen()
            self.sitzung = sitzung
        if self.letzte_runden is None or runden != self.letzte_runden:
            if self.aktuell is not None and self.letzte_runden is not None and runden == self.letzte_runden + 1:
                self._abschliessen(grafik)
            self.letzte_runden = runden
            self._neue_runde(runden + 1)
        a = self.aktuell
        anteil = grafik.runden_anteil
        if not self.gestartet:                 # direkt nach der Linie steht der Anteil kurz noch bei 0,99
            if anteil < 0.5:
                self.gestartet = True
            else:
                return
        if grafik.in_boxengasse:
            a["box"] = True
        if not grafik.runde_gueltig:
            a["gueltig"] = False
        i = min(PUNKTE - 1, max(0, int(anteil * PUNKTE)))
        if a["tempo"][i] is None:
            a["tempo"][i] = round(physik.tempo_kmh, 1)
            a["gas"][i] = round(physik.gas, 2)
            a["bremse"][i] = round(physik.bremse, 2)
            a["gang"][i] = max(0, physik.gang - 1)
            a["zeit"][i] = grafik.i_aktuelle_zeit / 1000

    def _abschliessen(self, grafik):
        a = self.aktuell
        gefuellt = sum(v is not None for v in a["tempo"]) / PUNKTE
        if gefuellt < 0.85:
            return                              # Runde nicht vollständig gesehen
        for name in ("tempo", "gas", "bremse", "gang", "zeit"):
            _luecken_fuellen(a[name])
        a["zeit_ms"] = grafik.i_letzte_zeit if grafik.i_letzte_zeit > 0 else None
        if a["zeit_ms"] in self.ungueltige_zeiten:
            a["gueltig"] = False
        self.runden[a["nr"]] = a
        if a["gueltig"] and not a["box"] and a["zeit_ms"]:
            beste = self.runden.get(self.beste_nr)
            if beste is None or a["zeit_ms"] < beste["zeit_ms"]:
                self.beste_nr = a["nr"]
        # alte Runden wegwerfen, die Bestrunde bleibt
        for nr in sorted(self.runden)[:-MAX_RUNDEN]:
            if nr != self.beste_nr:
                del self.runden[nr]

    def ungueltig_markieren(self, zeit_ms):
        """Eine Runde nachträglich als ungültig markieren (z. B. Track Limits, über die Zeitnahme erkannt)."""
        if not zeit_ms:
            return
        self.ungueltige_zeiten.add(zeit_ms)
        for nr, spur in self.runden.items():
            if spur.get("zeit_ms") == zeit_ms:
                spur["gueltig"] = False
        # Bestrunde neu bestimmen
        gute = [(spur["zeit_ms"], nr) for nr, spur in self.runden.items()
                if spur["gueltig"] and not spur["box"] and spur.get("zeit_ms")]
        self.beste_nr = min(gute)[1] if gute else None

    def letzte(self):
        if not self.runden:
            return None
        return self.runden[max(self.runden)]

    def beste(self):
        return self.runden.get(self.beste_nr)

    def export(self, laenge_m=None):
        """Alles als einfache Daten (für das Fenster und die Datei)."""
        return {"laenge": laenge_m, "beste": self.beste_nr,
                "runden": {str(nr): {"tempo": [round(v) for v in spur["tempo"]],
                                     "gas": spur["gas"], "bremse": spur["bremse"],
                                     "zeit": [round(v, 2) for v in spur["zeit"]],
                                     "gueltig": spur["gueltig"], "box": spur["box"], "zeit_ms": spur["zeit_ms"]}
                           for nr, spur in self.runden.items()}}


def _luecken_fuellen(werte):
    """Fehlende Stellen mit dem letzten bekannten Wert füllen."""
    letzter = next((w for w in werte if w is not None), 0)
    for i, w in enumerate(werte):
        if w is None:
            werte[i] = letzter
        else:
            letzter = w


# ---------------------------------------------------------------------------
# Auswertung: Kurven finden und zwei Runden vergleichen
# ---------------------------------------------------------------------------
def _glaetten(werte, breite=3):
    n = len(werte)
    return [sum(werte[(i + k) % n] for k in range(-breite, breite + 1)) / (2 * breite + 1) for i in range(n)]


def kurven_finden(spur):
    """Gibt die Stellen (Index) der Kurvenscheitel zurück: wo das Tempo deutlich einbricht."""
    tempo = _glaetten(spur["tempo"], 4)
    n = len(tempo)
    fenster = 30
    scheitel = []
    for i in range(n):
        umgebung = [tempo[(i + k) % n] for k in range(-fenster, fenster + 1)]
        if tempo[i] != min(umgebung):
            continue
        vorher = max(tempo[(i - k) % n] for k in range(1, fenster * 2))
        if vorher - tempo[i] >= 20:
            if scheitel and i - scheitel[-1] < 15:
                continue
            scheitel.append(i)
    return scheitel


def _zeit_bei(spur, i):
    return spur["zeit"][i]


def vergleichen(runde, beste, laenge_m=None):
    """Vergleicht eine Runde mit der Bestrunde Kurve für Kurve.
    Gibt eine Liste von dicts zurück, sortiert nach Zeitverlust (größter zuerst)."""
    scheitel = kurven_finden(beste)
    if not scheitel:
        return []
    meter = (laenge_m or 5000) / PUNKTE
    ergebnisse = []
    for k, s in enumerate(scheitel):
        start = 0 if k == 0 else (scheitel[k - 1] + s) // 2
        ende = PUNKTE - 1 if k == len(scheitel) - 1 else (s + scheitel[k + 1]) // 2
        verlust = ((_zeit_bei(runde, ende) - _zeit_bei(runde, start))
                   - (_zeit_bei(beste, ende) - _zeit_bei(beste, start)))

        def bremspunkt(spur):
            for i in range(start, s + 1):
                if spur["bremse"][i] > 0.2:
                    return i
            return None

        def gaspunkt(spur):
            for i in range(s, ende + 1):
                if spur["gas"][i] > 0.9:
                    return i
            return None

        def scheiteltempo(spur):
            return min(spur["tempo"][max(start, s - 10):min(ende, s + 10) + 1])

        b_r, b_b = bremspunkt(runde), bremspunkt(beste)
        g_r, g_b = gaspunkt(runde), gaspunkt(beste)
        ergebnisse.append({
            "kurve": k + 1, "scheitel": s, "start": start, "ende": ende,
            "verlust": round(verlust, 3),
            "bremsen_m": round((b_r - b_b) * meter) if b_r is not None and b_b is not None else None,
            "gas_m": round((g_r - g_b) * meter) if g_r is not None and g_b is not None else None,
            "tempo_diff": round(scheiteltempo(runde) - scheiteltempo(beste), 1),
        })
    return sorted(ergebnisse, key=lambda e: -e["verlust"])


def grund_text(e):
    """Warum ging in dieser Kurve Zeit verloren? Ein kurzer Satzteil oder ''."""
    if e["bremsen_m"] is not None and e["bremsen_m"] <= -8:
        return L(f"du bremst etwa {-e['bremsen_m']} Meter früher", f"you brake about {-e['bremsen_m']} metres earlier")
    if e["tempo_diff"] <= -3:
        return L(f"du bist im Scheitel {round(-e['tempo_diff'])} km/h langsamer", f"you are {round(-e['tempo_diff'])} km/h slower at the apex")
    if e["gas_m"] is not None and e["gas_m"] >= 8:
        return L(f"du gehst etwa {e['gas_m']} Meter später aufs Gas", f"you get on the throttle about {e['gas_m']} metres later")
    if e["bremsen_m"] is not None and e["bremsen_m"] >= 8 and e["tempo_diff"] <= 0:
        return L("du bremst zu spät und kommst schlecht um die Kurve", "you brake too late and don't get round the corner well")
    return ""
