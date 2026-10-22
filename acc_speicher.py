# acc_speicher.py
# Liest die Daten, die ACC in den Arbeitsspeicher schreibt (Shared Memory).
# Diese Datei startet man nicht selbst. Andere Skripte benutzen sie mit:
#     from acc_speicher import AccSpeicher
#
# Die Reihenfolge der Werte in den Bauplänen ist von ACC vorgegeben und
# MUSS genau stimmen. Auch Werte, die wir nicht brauchen, müssen deshalb
# drinstehen, sonst verrutscht alles, was danach kommt.
#
# Reifen/Räder sind immer in der Reihenfolge: vorne links, vorne rechts,
# hinten links, hinten rechts.

import ctypes

T15 = ctypes.c_wchar * 15     # Text mit 15 Zeichen
T33 = ctypes.c_wchar * 33     # Text mit 33 Zeichen
I = ctypes.c_int              # ganze Zahl
F = ctypes.c_float            # Kommazahl
F3, F4 = F * 3, F * 4

# Status-Werte (grafik.status)
STATUS_AUS, STATUS_REPLAY, STATUS_LIVE, STATUS_PAUSE = 0, 1, 2, 3

# Session-Arten (grafik.session)
SESSION_TRAINING, SESSION_QUALI, SESSION_RENNEN = 0, 1, 2

# Flaggen (grafik.flagge)
FLAGGE_KEINE, FLAGGE_BLAU, FLAGGE_GELB, FLAGGE_SCHWARZ, FLAGGE_WEISS = 0, 1, 2, 3, 4
FLAGGE_ZIEL, FLAGGE_STRAFE, FLAGGE_GRUEN, FLAGGE_ORANGE = 5, 6, 7, 8

# Regenstärke (grafik.regen, regen_10min, regen_30min)
REGEN = ["kein Regen", "Nieselregen", "leichter Regen", "mittlerer Regen",
         "starker Regen", "Gewitter"]

# Streckenzustand (grafik.grip_status)
GRIP = ["grün", "schnell", "optimal", "schmierig", "feucht", "nass", "überflutet"]


class Physik(ctypes.Structure):
    """Bereich 'physics': Werte vom Auto, ändern sich ständig."""
    _pack_ = 4
    _fields_ = [
        ("packet_id", I),
        ("gas", F),
        ("bremse", F),
        ("tank", F),                    # Liter im Tank
        ("gang", I),                    # 0 = R, 1 = N, 2 = 1. Gang ...
        ("drehzahl", I),
        ("lenkwinkel", F),
        ("tempo_kmh", F),
        ("geschwindigkeit", F3),
        ("g_kraft", F3),
        ("radschlupf", F4),
        ("radlast", F4),
        ("reifendruck", F4),            # psi
        ("raddrehzahl", F4),
        ("reifenverschleiss", F4),
        ("reifenschmutz", F4),
        ("reifen_kerntemp", F4),        # °C
        ("sturz", F4),
        ("federweg", F4),
        ("drs", F),
        ("tc_wert", F),
        ("richtung", F),
        ("nicken", F),
        ("rollen", F),
        ("schwerpunkt", F),
        ("schaden", F * 5),             # vorne, hinten, links, rechts, mitte
        ("reifen_neben_strecke", I),
        ("pitlimiter", I),              # 1 = an
        ("abs_wert", F),
        ("kers_ladung", F),
        ("kers_eingang", F),
        ("auto_schaltung", I),
        ("fahrzeughoehe", F * 2),
        ("turbo", F),
        ("ballast", F),
        ("luftdichte", F),
        ("luft_temp", F),                # °C
        ("strecken_temp", F),            # °C
        ("drehrate", F3),
        ("force_feedback", F),
        ("leistungsmesser", F),
        ("motorbremse", I),
        ("ers_1", I), ("ers_2", I), ("ers_3", I), ("ers_4", I),
        ("kers_kj", F),
        ("drs_verfuegbar", I),
        ("drs_an", I),
        ("brems_temp", F4),              # °C
        ("kupplung", F),
        ("reifentemp_innen", F4),
        ("reifentemp_mitte", F4),
        ("reifentemp_aussen", F4),
        ("ki_faehrt", I),
        ("kontakt_punkt", F3 * 4),
        ("kontakt_normal", F3 * 4),
        ("kontakt_richtung", F3 * 4),
        ("bremsbalance", F),            # 0.0 bis 1.0, Anteil vorne
        ("lokale_geschwindigkeit", F3),
        ("p2p_1", I), ("p2p_2", I),
        ("max_drehzahl_aktuell", I),
        ("mz", F4), ("fx", F4), ("fy", F4),
        ("schlupfverhaeltnis", F4),
        ("schlupfwinkel", F4),
        ("tc_greift", I),
        ("abs_greift", I),
        ("aufhaengung_schaden", F4),
        ("reifentemp", F4),
        ("wasser_temp", F),              # °C
        ("bremsdruck", F4),
        ("bremsmischung_vorne", I),
        ("bremsmischung_hinten", I),
        ("belag", F4),                  # Bremsbelag in mm
        ("scheibe", F4),                # Bremsscheibe in mm
    ]


class Grafik(ctypes.Structure):
    """Bereich 'graphics': Session, Runden, Zeiten, Flaggen, Wetter, Elektronik."""
    _pack_ = 4
    _fields_ = [
        ("packet_id", I),
        ("status", I),                    # siehe STATUS_... oben
        ("session", I),
        ("aktuelle_zeit", T15),
        ("letzte_zeit", T15),
        ("beste_zeit", T15),
        ("split", T15),
        ("runden_fertig", I),             # abgeschlossene Runden
        ("position", I),
        ("i_aktuelle_zeit", I),           # Zeiten in Millisekunden
        ("i_letzte_zeit", I),
        ("i_beste_zeit", I),
        ("session_rest", F),              # Restzeit der Session in Millisekunden
        ("strecke_gefahren", F),
        ("in_box", I),                    # steht in der Box
        ("sektor", I),
        ("letzter_sektor", I),
        ("runden_gesamt", I),             # Renndistanz bei Runden-Rennen, sonst 0
        ("reifen_mischung", T33),
        ("replay_faktor", F),
        ("runden_anteil", F),             # 0.0 = Start/Ziel, 0.5 = halbe Runde
        ("aktive_autos", I),
        ("auto_koordinaten", F * 180),
        ("auto_ids", I * 60),
        ("spieler_auto_id", I),
        ("strafzeit", F),
        ("flagge", I),                    # siehe FLAGGE_... oben
        ("strafe", I),                    # Art der Strafe, 0 = keine
        ("ideallinie", I),
        ("in_boxengasse", I),             # fährt durch die Boxengasse
        ("grip", F),
        ("pflichtstopp_erledigt", I),
        ("wind_tempo", F),
        ("wind_richtung", F),
        ("setup_menue", I),
        ("display_1", I),
        ("display_2", I),
        ("tc", I),
        ("tc_cut", I),
        ("motor_map", I),
        ("abs", I),
        ("sprit_pro_runde", F),           # ACCs eigene Schätzung (Liter/Runde)
        ("regenlicht", I),
        ("lichthupe", I),
        ("lichtstufe", I),
        ("abgastemperatur", F),
        ("wischer", I),
        ("stint_gesamt_rest", I),         # Millisekunden, -1 = kein Limit
        ("fahrer_stint_rest", I),
        ("regenreifen", I),
        ("session_index", I),
        ("sprit_verbraucht", F),
        ("delta_text", T15),
        ("i_delta", I),                   # Delta zur Bestzeit in ms
        ("geschaetzte_zeit", T15),
        ("i_geschaetzte_zeit", I),
        ("delta_positiv", I),
        ("i_split", I),
        ("runde_gueltig", I),
        ("sprit_runden_geschaetzt", F),   # ACCs Schätzung: Runden mit dem Tank
        ("streckenstatus", T33),
        ("fehlende_pflichtstopps", I),
        ("uhrzeit", F),                   # Uhrzeit im Spiel in Sekunden
        ("blinker_links", I),
        ("blinker_rechts", I),
        ("gelb_global", I),
        ("gelb_sektor_1", I),
        ("gelb_sektor_2", I),
        ("gelb_sektor_3", I),
        ("weiss_global", I),
        ("gruen_global", I),
        ("ziel_global", I),
        ("rot_global", I),
        ("mfd_reifensatz", I),
        ("mfd_sprit", F),                 # im Boxenmenü eingestellte Spritmenge
        ("mfd_druck_vl", F),
        ("mfd_druck_vr", F),
        ("mfd_druck_hl", F),
        ("mfd_druck_hr", F),
        ("grip_status", I),              # siehe GRIP oben
        ("regen", I),                     # siehe REGEN oben
        ("regen_10min", I),
        ("regen_30min", I),
        ("reifensatz", I),
        ("strategie_reifensatz", I),
    ]


class Statisch(ctypes.Structure):
    """Bereich 'static': Werte, die sich während einer Session nicht ändern."""
    _pack_ = 4
    _fields_ = [
        ("sm_version", T15),
        ("ac_version", T15),
        ("anzahl_sessions", I),
        ("anzahl_autos", I),
        ("auto", T33),
        ("strecke", T33),
        ("fahrer_name", T33),
        ("fahrer_nachname", T33),
        ("fahrer_nick", T33),
        ("sektoren", I),
        ("max_drehmoment", F),
        ("max_leistung", F),
        ("max_drehzahl", I),
        ("tank_max", F),                  # Tankgröße in Litern
        ("federweg", F4),
        ("reifenradius", F4),
        ("max_turbo", F),
        ("veraltet_1", F),
        ("veraltet_2", F),
        ("strafen_an", I),
        ("verbrauchs_faktor", F),         # 0 = Spritverbrauch aus, 1 = normal
        ("reifen_faktor", F),
        ("schaden_faktor", F),
        ("heizdecken", I),
        ("stabilitaet", F),
        ("auto_kupplung", I),
        ("auto_zwischengas", I),
        ("hat_drs", I),
        ("hat_ers", I),
        ("hat_kers", I),
        ("kers_max", F),
        ("motorbremse_stufen", I),
        ("ers_stufen", I),
        ("spline_laenge", F),
        ("strecken_variante", T33),
        ("ers_max", F),
        ("zeitrennen", I),                # 1 = Rennen nach Zeit
        ("extrarunde", I),                # 1 = nach Zeitablauf noch eine Runde
        ("auto_lackierung", T33),
        ("umgekehrtes_grid", I),
        ("boxenfenster_start", I),
        ("boxenfenster_ende", I),
        ("online", I),
    ]


class AccSpeicher:
    """Öffnet die drei Speicherbereiche von ACC und liest sie aus.

    Die Bereiche werden nur geöffnet, wenn ACC sie schon angelegt hat.
    So stört das Programm ACC nicht, wenn es vor dem Spiel gestartet wird.
    Solange ACC nicht läuft, liefert lesen() leere Werte (status = 0)."""

    NAMEN = (("acpmf_physics", Physik), ("acpmf_graphics", Grafik), ("acpmf_static", Statisch))

    def __init__(self):
        self._adressen = None
        self._naechster_versuch = 0.0

    def _oeffnen(self):
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenFileMappingW.restype = ctypes.c_void_p
        kernel32.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.MapViewOfFile.restype = ctypes.c_void_p
        kernel32.MapViewOfFile.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                           ctypes.c_uint32, ctypes.c_size_t]
        nur_lesen = 4
        adressen = []
        for name, _ in self.NAMEN:
            griff = kernel32.OpenFileMappingW(nur_lesen, False, "Local\\" + name)
            if not griff:
                return None             # ACC hat den Bereich noch nicht angelegt
            adresse = kernel32.MapViewOfFile(griff, nur_lesen, 0, 0, 0)
            if not adresse:
                return None
            adressen.append(adresse)
        return adressen

    def lesen(self):
        """Gibt (physik, grafik, statisch) mit den aktuellen Werten zurück."""
        import time
        if self._adressen is None and time.monotonic() >= self._naechster_versuch:
            self._adressen = self._oeffnen()
            self._naechster_versuch = time.monotonic() + 1.0
        ergebnis = []
        for i, (_, bauplan) in enumerate(self.NAMEN):
            groesse = ctypes.sizeof(bauplan)
            if self._adressen is None:
                ergebnis.append(bauplan.from_buffer_copy(bytes(groesse)))
            else:
                ergebnis.append(bauplan.from_buffer_copy(ctypes.string_at(self._adressen[i], groesse)))
        return tuple(ergebnis)
