# acc_funktaste.py
# Liest die Funktaste: eine Taste am Lenkrad (oder Button-Box) oder eine Taste auf der Tastatur.
#
# Wichtig: Wir benutzen hier die einfache Windows-Joystick-Abfrage (winmm).
# Die kann das Lenkrad nur LESEN. Sie übernimmt es nicht und fasst das
# Force Feedback nicht an. (pygame/SDL hat das Lenkrad so geöffnet, dass ACC
# kein Force Feedback mehr hatte.)
#
# Diese Datei startet man nicht selbst.

import ctypes
import json
import os
import time
from ctypes import wintypes
from acc_sprache import L

ORDNER = os.path.dirname(os.path.abspath(__file__))
FUNK_DATEI = os.path.join(ORDNER, "funk_einstellungen.json")

JOY_RETURNBUTTONS = 0x80
JOY_RETURNPOV = 0x40
POV_MITTE = 0xFFFF
POV_RICHTUNGEN = L({0: "hoch", 9000: "rechts", 18000: "runter", 27000: "links"},
                   {0: "up", 9000: "right", 18000: "down", 27000: "left"})


class JOYINFOEX(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("dwXpos", wintypes.DWORD), ("dwYpos", wintypes.DWORD),
                ("dwZpos", wintypes.DWORD), ("dwRpos", wintypes.DWORD),
                ("dwUpos", wintypes.DWORD), ("dwVpos", wintypes.DWORD),
                ("dwButtons", wintypes.DWORD), ("dwButtonNumber", wintypes.DWORD),
                ("dwPOV", wintypes.DWORD), ("dwReserved1", wintypes.DWORD),
                ("dwReserved2", wintypes.DWORD)]


class JOYCAPSW(ctypes.Structure):
    _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD),
                ("szPname", wintypes.WCHAR * 32)] + \
               [(n, wintypes.UINT) for n in (
                   "wXmin", "wXmax", "wYmin", "wYmax", "wZmin", "wZmax", "wNumButtons",
                   "wPeriodMin", "wPeriodMax", "wRmin", "wRmax", "wUmin", "wUmax",
                   "wVmin", "wVmax", "wCaps", "wMaxAxes", "wNumAxes", "wMaxButtons")] + \
               [("szRegKey", wintypes.WCHAR * 32), ("szOEMVxD", wintypes.WCHAR * 260)]


# ---------------------------------------------------------------------------
# Lenkräder und Controller
# ---------------------------------------------------------------------------
def _winmm():
    return ctypes.windll.winmm


def _geraete_name(vid, pid, standard):
    """Den echten Namen (z. B. 'FANATEC CSL DD') steht in der Registry."""
    import winreg
    pfad = (r"System\CurrentControlSet\Control\MediaProperties\PrivateProperties"
            rf"\Joystick\OEM\VID_{vid:04X}&PID_{pid:04X}")
    for wurzel in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(wurzel, pfad) as schluessel:
                name = winreg.QueryValueEx(schluessel, "OEMName")[0]
                if name:
                    return name
        except OSError:
            pass
    return standard


def lenkraeder():
    """Liste aller angeschlossenen Controller: (nummer, vid, pid, name)."""
    winmm = _winmm()
    gefunden = []
    for nummer in range(winmm.joyGetNumDevs()):
        info = JOYINFOEX(dwSize=ctypes.sizeof(JOYINFOEX), dwFlags=JOY_RETURNBUTTONS)
        if winmm.joyGetPosEx(nummer, ctypes.byref(info)) != 0:
            continue                      # an dieser Stelle steckt nichts
        faehigkeiten = JOYCAPSW()
        winmm.joyGetDevCapsW(nummer, ctypes.byref(faehigkeiten), ctypes.sizeof(faehigkeiten))
        name = _geraete_name(faehigkeiten.wMid, faehigkeiten.wPid,
                             faehigkeiten.szPname or f"Controller {nummer + 1}")
        gefunden.append((nummer, faehigkeiten.wMid, faehigkeiten.wPid, name))
    return gefunden


def _lenkrad_zustand(nummer):
    """Gibt (tasten-bitmaske, pov) zurück oder None, wenn das Gerät weg ist."""
    info = JOYINFOEX(dwSize=ctypes.sizeof(JOYINFOEX), dwFlags=JOY_RETURNBUTTONS | JOY_RETURNPOV)
    if _winmm().joyGetPosEx(nummer, ctypes.byref(info)) != 0:
        return None
    return info.dwButtons, info.dwPOV


# ---------------------------------------------------------------------------
# Tastatur
# ---------------------------------------------------------------------------
NICHT_ERLAUBT = {0x01, 0x02, 0x04, 0x05, 0x06,   # Maustasten
                 0x10, 0x11, 0x12}                # Shift/Strg/Alt allgemein (es gibt links/rechts)


def _taste_gedrueckt(vk):
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def tasten_name(vk):
    user32 = ctypes.windll.user32
    scan = user32.MapVirtualKeyW(vk, 0)
    puffer = ctypes.create_unicode_buffer(64)
    if scan and user32.GetKeyNameTextW(scan << 16, puffer, 64):
        return puffer.value
    return L(f"Taste {vk}", f"Key {vk}")


# ---------------------------------------------------------------------------
# Die Funktaste
# ---------------------------------------------------------------------------
def gespeichert_laden():
    try:
        with open(FUNK_DATEI, encoding="utf-8") as datei:
            return json.load(datei)
    except (OSError, ValueError):
        return None


def beschreibung():
    daten = gespeichert_laden()
    if not daten or "art" not in daten:
        return L("noch nicht festgelegt", "not set yet")
    if daten["art"] == "tastatur":
        return L(f'Tastatur: {daten["name"]}', f'Keyboard: {daten["name"]}')
    if daten["art"] == "pov":
        return L(f'Steuerkreuz {POV_RICHTUNGEN.get(daten["richtung"], "")} an {daten["name"]}', f'D-pad {POV_RICHTUNGEN.get(daten["richtung"], "")} on {daten["name"]}')
    return L(f'Taste {daten["knopf"] + 1} an {daten["name"]}', f'Button {daten["knopf"] + 1} on {daten["name"]}')


class Funktaste:
    """Fragt ab, ob die gespeicherte Funktaste gerade gedrückt ist."""

    def __init__(self):
        self.daten = gespeichert_laden()
        if not self.daten or "art" not in self.daten:
            raise LookupError(L("Keine Funktaste festgelegt. Bitte unter Einstellungen festlegen.", "No radio button set. Please set one in the settings."))
        self.nummer = None
        self._naechste_suche = 0.0
        if self.daten["art"] != "tastatur":
            self._suchen()
            if self.nummer is None:
                raise LookupError(L(f'{self.daten["name"]} nicht gefunden. Ist es eingesteckt?', f'{self.daten["name"]} not found. Is it plugged in?'))

    def _suchen(self):
        """Das Lenkrad über Hersteller- und Gerätenummer wiederfinden
        (die Platznummer in Windows kann sich nach dem Umstecken ändern)."""
        self.nummer = None
        for nummer, vid, pid, _ in lenkraeder():
            if vid == self.daten["vid"] and pid == self.daten["pid"]:
                self.nummer = nummer
                return

    def gedrueckt(self):
        art = self.daten["art"]
        if art == "tastatur":
            return _taste_gedrueckt(self.daten["vk"])
        zustand = _lenkrad_zustand(self.nummer) if self.nummer is not None else None
        if zustand is None:                     # kurz weg? Alle 2 Sekunden neu suchen
            if time.monotonic() >= self._naechste_suche:
                self._naechste_suche = time.monotonic() + 2
                self._suchen()
            return False
        tasten, pov = zustand
        if art == "pov":
            return pov == self.daten["richtung"]
        return bool(tasten & (1 << self.daten["knopf"]))


def lernen(abbruch_nach=15.0):
    """Wartet, bis eine Taste am Lenkrad, ein Steuerkreuz oder eine Tastatur-Taste
    gedrückt wird, und speichert sie. Gibt die Beschreibung zurück oder None."""
    geraete = lenkraeder()

    def momentaufnahme():
        gedrueckt = set()
        for nummer, vid, pid, name in geraete:
            zustand = _lenkrad_zustand(nummer)
            if zustand is None:
                continue
            tasten, pov = zustand
            for knopf in range(32):
                if tasten & (1 << knopf):
                    gedrueckt.add(("knopf", nummer, knopf))
            if pov in POV_RICHTUNGEN:
                gedrueckt.add(("pov", nummer, pov))
        for vk in range(1, 255):
            if vk not in NICHT_ERLAUBT and _taste_gedrueckt(vk):
                gedrueckt.add(("tastatur", None, vk))
        return gedrueckt

    schon_gedrueckt = momentaufnahme()        # Dauerschalter ignorieren
    ende = time.monotonic() + abbruch_nach
    while time.monotonic() < ende:
        neu = momentaufnahme() - schon_gedrueckt
        if neu:
            art, nummer, wert = sorted(neu, key=lambda e: (e[0] == "tastatur", str(e)))[0]
            if art == "tastatur":
                daten = {"art": "tastatur", "vk": wert, "name": tasten_name(wert)}
            else:
                _, vid, pid, name = next(g for g in geraete if g[0] == nummer)
                daten = {"art": art, "vid": vid, "pid": pid, "name": name}
                daten["knopf" if art == "knopf" else "richtung"] = wert
            with open(FUNK_DATEI, "w", encoding="utf-8") as datei:
                json.dump(daten, datei, ensure_ascii=False)
            return beschreibung()
        time.sleep(0.01)
    return None
