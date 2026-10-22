# acc_ki.py
# Das KI-Gehirn des Renningenieurs.
# Läuft kostenlos und offline über Ollama (https://ollama.com) auf deiner Grafikkarte.
#
# So arbeitet es:
#   - Bei jeder Frage bekommt die KI ALLE aktuellen Daten: das ganze Feld in der
#     Wertung und in der Reihenfolge auf der Strecke, Sprit-Strategie, Reifen,
#     Bremsen, Schaden, Wetter, Flaggen, Elektronik usw.
#   - Sie merkt sich die letzten Fragen, damit Nachfragen funktionieren
#     ("Und der dahinter?").
#   - Die Antwort kommt Satz für Satz (Streaming). Der erste Satz wird schon
#     gesprochen, während die KI noch weiterschreibt.
#   - Alles, was gerechnet werden muss (Abstände, Sprit, Boxenfenster), rechnet
#     das Programm vorher selbst. Die KI muss nur noch verstehen und erklären.
#
# Diese Datei startet man nicht selbst.

import json
import re
import time
import urllib.request
from collections import deque

import acc_renningenieur as ri
from acc_sprache import L

OLLAMA = "http://127.0.0.1:11434"

KI_MODELLE = [
    ("gemma3:4b", L("Gemma 3 4B (schnell, 3,3 GB, für kleinere Grafikkarten)",
                    "Gemma 3 4B (fast, 3.3 GB, for smaller graphics cards)")),
    ("gemma3:12b", L("Gemma 3 12B (viel klüger, 8 GB, empfohlen ab 12 GB Grafikspeicher)",
                     "Gemma 3 12B (much smarter, 8 GB, recommended from 12 GB VRAM)")),
    ("qwen2.5:7b", "Qwen 2.5 7B (4,7 GB)"),
]

SYSTEM = L("""Du bist der Renningenieur eines Fahrers in Assetto Corsa Competizione und sprichst mit ihm über Funk.
Seine Sätze kommen aus einer Spracherkennung und können kleine Fehler enthalten. Überlege, was er meint.

So antwortest du:
- Auf Deutsch, klar und freundlich wie ein echter Renningenieur am Funk: ruhig, knapp, präzise,
  mit dem typischen Funk-Wortschatz, wo er passt ("Copy", "Box, Box", "Lücke", "Windschatten",
  "Pace", "Stint", "Delta", "sauber bleiben", "Rhythmus halten", "Reifen schonen", "Druck machen").
  Wechsle die Formulierungen ab, damit es nicht eintönig klingt.
- Formuliere IMMER ganze, vollständige Sätze. Keine Stichpunkte und keine nackten Zahlen.
  Falsch: "Vorne 1,5, hinten 2,0." Richtig: "Der Abstand zum Vordermann beträgt 1,5 Sekunden,
  und der Hintermann ist 2,0 Sekunden hinter dir."
  Falsch: "Reifen 26, 26, 27, 27." Richtig: "Der Reifen vorne links hat 26 PSI, vorne rechts 26 PSI,
  hinten links 27 PSI und hinten rechts 27 PSI."
- Halte dich trotzdem kurz: meistens zwei bis drei Sätze, bei mehreren Fragen entsprechend mehr.
- Beantworte ALLE Teile der Frage, wenn er mehrere Dinge auf einmal fragt.
- Manchmal fragt er nicht, sondern meldet etwas ("Ich bin in der Box", "Die Reifen rutschen",
  "Ich habe mich gedreht"). Dann reagierst du wie ein Ingenieur: kurz bestätigen und sagen,
  was jetzt zu tun ist, mit den passenden Zahlen aus den Daten.
- Werte die Daten wirklich aus, statt nur Zahlen vorzulesen: sag, was sie bedeuten und warum.
  Beispiel: "Du holst auf ihn auf, weil du pro Runde drei Zehntel schneller bist."
- Unter PASSENDE FAKTEN steht, was das Programm zu seiner Frage schon berechnet hat. Nutze es,
  wenn es passt. Hat das Programm die Frage falsch verstanden, ignoriere es.
- Beantworte NUR, was er gefragt hat. Fang keine anderen Themen an. Motor, Wassertemperatur,
  Elektronik (TC, ABS, Motor-Map) und Setup sprichst du von dir aus NIE an und schlägst dort
  NIE Änderungen vor. Probleme erwähnst du nur, wenn sie unter WARNUNGEN stehen.
- Jede Frage ist neu. Wiederhole nicht, was du vorher gesagt hast, die Daten haben sich geändert.
- Benutze nur Zahlen und Fakten aus den AKTUELLEN DATEN. Erfinde nichts und rechne nicht neu,
  die Werte sind schon fertig berechnet. Fehlt etwas, sag kurz, dass du es nicht weißt.
- Unterscheide genau: "Wertung" ist die Platzierung im Rennen. "Strecke" ist, wer gerade physisch
  vor oder hinter ihm fährt, auch wenn das Auto eine Runde vor oder zurück ist.
- Positive Abstände heißen "vor dir", negative "hinter dir". "R" heißt Runden.
- Bei Fragen nach Rat oder Taktik: gib eine klare Empfehlung mit kurzem Grund aus den Daten.
- Bei Fragen zu Abständen, Position oder Lage beende die Antwort oft mit einem kurzen taktischen
  oder motivierenden Satz, der zur Lage passt, so wie ein echter Renningenieur. Zum Beispiel:
  "Nach hinten hast du genug Abstand, konzentrier dich auf den Wagen vor dir." oder
  "Der Hintermann macht Druck, bleib sauber an den Kurvenausgängen." Nutz dafür den TAKTIK-HINWEIS
  aus den Daten, formuliere ihn aber jedes Mal etwas anders. Nicht bei reinen Technikfragen.
- Zahlen mit Komma (1,4 Sekunden), Rundenzeiten wie "2 Minuten 18,5 Sekunden".
  Plätze als "Platz 3", nicht als "P3". Immer mit Einheit (Sekunden, Liter, Grad, PSI, Runden).
- Fang NIE mit einer Begrüßung an (kein "Guten Abend", "Hallo", "Hi"). Ihr seid mitten im Rennen,
  antworte sofort mit dem Inhalt. Keine Füllwörter wie "Ähm" oder "Hmm".
- Sag bei Abständen immer "Abstand", nie "Luft" (also "du hast genug Abstand", nicht "genug Luft").
- Steht bei einem Fahrer kein Name, nenn ihn "das Auto auf Platz X". Erfinde keine Namen.
- Keine Aufzählungszeichen, keine Emojis, kein Markdown, keine Rückfragen
  außer es ist wirklich unklar.
- Musik- und Funkbefehle (Musik aus, Funkstille ...) erledigt das Programm selbst. Geh nicht darauf ein.
""", """You are the race engineer of a driver in Assetto Corsa Competizione and you talk to him over the radio.
His sentences come from speech recognition and can contain small errors. Think about what he means.

How you answer:
- In English, clear and friendly like a real race engineer on the radio: calm, short, precise,
  with typical radio language where it fits ("copy", "box, box", "gap", "slipstream", "pace",
  "stint", "delta", "stay clean", "keep the rhythm", "look after the tyres", "push now").
  Vary your phrasing so it doesn't sound repetitive.
- ALWAYS use complete sentences. No bullet points and no bare numbers.
  Wrong: "Ahead 1.5, behind 2.0." Right: "The gap to the car ahead is 1.5 seconds,
  and the car behind is 2.0 seconds back."
  Wrong: "Tyres 26, 26, 27, 27." Right: "Front left is at 26 PSI, front right 26 PSI,
  rear left 27 PSI and rear right 27 PSI."
- Still keep it short: usually two or three sentences, more if he asks several things.
- Answer ALL parts of the question if he asks several things at once.
- Sometimes he doesn't ask but reports something ("I'm in the pits", "The tyres are sliding",
  "I spun"). Then react like an engineer: briefly acknowledge and say what to do now,
  with the relevant numbers from the data.
- Really evaluate the data instead of just reading out numbers: say what they mean and why.
  Example: "You're catching him because you're three tenths a lap faster."
- RELEVANT FACTS contains what the program has already calculated for his question. Use it
  if it fits. If the program misunderstood the question, ignore it.
- Answer ONLY what he asked. Don't start other topics. You NEVER bring up the engine, water
  temperature, electronics (TC, ABS, engine map) or setup on your own and NEVER suggest
  changes there. Only mention problems if they are listed under WARNINGS.
- Every question is new. Don't repeat what you said before, the data has changed.
- Only use numbers and facts from the CURRENT DATA. Don't invent anything and don't recalculate,
  the values are already calculated. If something is missing, briefly say you don't know.
- Distinguish carefully: "Standings" is the race position. "On track" is who is physically
  directly ahead of or behind him, even if that car is a lap up or down.
- Positive gaps mean "ahead of you", negative ones "behind you". "L" means laps.
- For questions about advice or tactics: give a clear recommendation with a short reason from the data.
- For questions about gaps, position or the situation, often end with a short tactical or
  motivating sentence that fits the situation, like a real race engineer. For example:
  "You have enough gap behind, focus on the car ahead." or
  "The car behind is pushing, stay clean on the corner exits." Use the TACTICAL HINT
  from the data for this, but phrase it a bit differently each time. Not for pure technical questions.
- Numbers with a decimal point (1.4 seconds), lap times like "2 minutes 18.5 seconds".
  Positions as "P3". Always with units (seconds, litres, degrees, PSI, laps).
- NEVER start with a greeting (no "Good evening", "Hello", "Hi"). You're in the middle of the race,
  answer straight away with the content. No filler words like "Um" or "Hmm".
- For gaps always say "gap", never "air".
- If a driver has no name, call him "the car in P X". Don't invent names.
- No bullet points, no emojis, no markdown, no follow-up questions
  unless something is really unclear.
- Music and radio commands (music off, radio silence ...) are handled by the program. Don't respond to them.
""")


# ---------------------------------------------------------------------------
# Verbindung zu Ollama
# ---------------------------------------------------------------------------
def _anfrage(pfad, daten=None, zeitlimit=5.0):
    roh = json.dumps(daten).encode() if daten is not None else None
    anfrage = urllib.request.Request(OLLAMA + pfad, data=roh,
                                     headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(anfrage, timeout=zeitlimit)


def installierte_modelle():
    """Liste der geladenen Modelle, oder None, wenn Ollama nicht läuft."""
    try:
        with _anfrage("/api/tags", zeitlimit=1.5) as antwort:
            return [m["name"] for m in json.load(antwort).get("models", [])]
    except Exception:
        return None


def modell_vorhanden(name, modelle=None):
    modelle = installierte_modelle() if modelle is None else modelle
    if not modelle:
        return False
    gesucht = name if ":" in name else name + ":latest"
    return gesucht in modelle


def modell_laden(name, fortschritt=None):
    """Lädt ein Modell herunter. fortschritt(prozent) wird zwischendurch aufgerufen."""
    with _anfrage("/api/pull", {"model": name, "stream": True}, zeitlimit=3600) as antwort:
        for zeile in antwort:
            if not zeile.strip():
                continue
            stand = json.loads(zeile)
            if "error" in stand:
                raise RuntimeError(stand["error"])
            if fortschritt and stand.get("total"):
                fortschritt(int(stand.get("completed", 0) * 100 / stand["total"]))
    return True


def aufwaermen(name):
    """Lädt das Modell schon mal in die Grafikkarte, damit die erste Antwort schnell kommt."""
    anfrage = {"model": name, "prompt": "", "keep_alive": "60m"}
    if AUF_PROZESSOR:
        anfrage["options"] = {"num_gpu": 0}
    with _anfrage("/api/generate", anfrage, zeitlimit=120) as antwort:
        antwort.read()


# ---------------------------------------------------------------------------
# Alle Daten als Text für die KI
# ---------------------------------------------------------------------------
def _sicher(funktion, *argumente):
    try:
        return funktion(*argumente)
    except Exception:
        return None


def _abstand_text(art, wert):
    if art is None or wert is None:
        return L("unbekannt", "unknown")
    if art == "runden":
        return f"{wert:+d} {L('R', 'L')}"
    return f"{ri.komma(wert)} s" if wert < 0 else f"+{ri.komma(wert)} s"


def _zeit(ms):
    return ri.zeit_sprechen(ms) if ri.gueltige_zeit(ms) else L("keine", "none")


def _ki_name(auto):
    nummer = f"#{auto.nummer} " if auto.nummer is not None else ""
    name = auto.fahrer if auto.fahrer and auto.fahrer != "?" else L("(Name unbekannt)", "(name unknown)")
    marke = ri.MARKEN.get(auto.modell)
    return nummer + name + (f" ({marke})" if marke else "")


def telemetrie_text(stand):
    """Alle wichtigen Daten in kompakter Form. Mit gehaltener Sperre aufrufen."""
    if not stand.acc_laeuft():
        return L("ACC läuft gerade nicht oder der Fahrer ist nicht auf der Strecke.", "ACC is not running right now or the driver is not on track.")
    g, p, s, acc = stand.grafik, stand.physik, stand.statisch, stand.acc
    session = {0: L("Training", "Practice"), 1: L("Qualifying", "Qualifying"), 2: L("Rennen", "Race")}.get(g.session, L("andere Session", "other session"))
    z = []

    # Session
    if g.in_box:
        ort = L("Er STEHT GERADE IN DER BOX (Boxenstopp läuft).", "He is STANDING IN THE PITS RIGHT NOW (pit stop in progress).")
    elif g.in_boxengasse:
        ort = L("Er fährt gerade durch die Boxengasse.", "He is driving through the pit lane right now.")
    else:
        ort = L("Er fährt auf der Strecke.", "He is driving on track.")
    z.append(L(f"LAGE JETZT: {ort}", f"SITUATION NOW: {ort}"))
    z.append("SESSION")
    z.append(L(f"Art: {session}. Strecke: {s.strecke}. Auto: {s.auto}.", f"Type: {session}. Track: {s.strecke}. Car: {s.auto}."))
    z.append(_sicher(ri.antwort_rest, stand) or "")
    z.append(_sicher(ri.antwort_runde, stand) or "")
    z.append(L(f"Flagge: {_sicher(ri.antwort_flagge, stand)} Strafe: {_sicher(ri.antwort_strafe, stand)}", f"Flag: {_sicher(ri.antwort_flagge, stand)} Penalty: {_sicher(ri.antwort_strafe, stand)}"))
    z.append(_sicher(ri.antwort_pflichtstopp, stand) or "")

    # Mein Auto
    z.append(L("\nFAHRER (du sprichst mit ihm)", "\nDRIVER (you are talking to him)"))
    z.append(_sicher(ri.antwort_position, stand) or "")
    z.append(L(f"Tempo {p.tempo_kmh:.0f} km/h, Gang {max(0, p.gang - 1)}, "
             f"{'in der Boxengasse' if g.in_boxengasse else 'auf der Strecke'}"
             f"{', Pitlimiter an' if p.pitlimiter else ''}.", f"Speed {p.tempo_kmh:.0f} km/h, gear {max(0, p.gang - 1)}, "
             f"{'in the pit lane' if g.in_boxengasse else 'on track'}"
             f"{', pit limiter on' if p.pitlimiter else ''}."))
    z.append(L(f"Letzte Runde {_zeit(g.i_letzte_zeit)}, Bestzeit {_zeit(g.i_beste_zeit)}, "
             f"Runde gerade {'gültig' if g.runde_gueltig else 'ungültig'}.", f"Last lap {_zeit(g.i_letzte_zeit)}, best lap {_zeit(g.i_beste_zeit)}, "
             f"current lap {'valid' if g.runde_gueltig else 'invalid'}."))
    z.append(_sicher(ri.antwort_delta, stand) or "")
    z.append(L("Sprit: ", "Fuel: ") + (_sicher(ri.antwort_sprit, stand) or "unbekannt"))
    z.append(L("Verbrauch: ", "Consumption: ") + (_sicher(ri.antwort_verbrauch, stand) or "unbekannt"))
    z.append(L("Strategie: ", "Strategy: ") + (_sicher(ri.antwort_box, stand) or "unbekannt"))
    z.append(L("Ohne Stopp: ", "Without a stop: ") + (_sicher(ri.antwort_spritsparen, stand) or "unbekannt"))
    z.append(L("Reifen: ", "Tyres: ") + (_sicher(ri.antwort_reifen, stand) or "unbekannt"))
    z.append(L("Bremsen: ", "Brakes: ") + " ".join(filter(None, [_sicher(ri.antwort_bremstemp, stand),
                                                   _sicher(ri.antwort_bremsbelag, stand)])))
    z.append(L("Schaden: ", "Damage: ") + (_sicher(ri.antwort_schaden, stand) or "unbekannt"))

    # Was wirklich ein Problem ist, berechnet das Programm selbst
    warnungen = (_sicher(warnungen_finden, stand) or []) + (_sicher(hinweise_finden, stand) or [])
    z.append(L("\nWARNUNGEN (nur diese Probleme gibt es, sonst ist am Auto alles in Ordnung)", "\nWARNINGS (only these problems exist, otherwise everything on the car is fine)"))
    z.append(" ".join(warnungen) if warnungen else L("Keine. Das Auto ist in Ordnung.", "None. The car is fine."))

    # Nur erwähnen, wenn der Fahrer danach fragt
    z.append(L("\nNUR AUF NACHFRAGE (von dir aus nie erwähnen und nie Änderungen vorschlagen)", "\nONLY IF ASKED (never mention on your own and never suggest changes)"))
    z.append(L("Elektronik: ", "Electronics: ") + (_sicher(ri.antwort_elektronik, stand) or "unbekannt"))
    z.append(_sicher(ri.antwort_wassertemp, stand) or "")

    # Wetter
    z.append(L("\nWETTER", "\nWEATHER"))
    z.append(_sicher(ri.antwort_wetter, stand) or "")
    z.append(_sicher(ri.antwort_grip, stand) or "")
    z.append(_sicher(ri.antwort_wind, stand) or "")

    # Das Feld in der Wertung
    if acc.verbindungs_id is not None:
        ich = acc.ich()
        liste = acc.rangliste()
        z.append(L("\nWERTUNG (Platz, Startnummer, Fahrer, Abstand zum Fahrer, letzte Runde, beste Runde)", "\nSTANDINGS (position, car number, driver, gap to the driver, last lap, best lap)"))
        for platz, auto in enumerate(liste, start=1):
            if auto is ich:
                z.append(L(f"P{platz} {_ki_name(auto)} = DER FAHRER", f"P{platz} {_ki_name(auto)} = THE DRIVER"))
                continue
            abstand = _abstand_text(*acc.abstand_zu(auto))
            box = L(", in der Box", ", in the pits") if auto.ort in (2, 3, 4) else ""
            z.append(L(f"P{platz} {_ki_name(auto)}, {abstand}, "
                     f"letzte {_zeit(auto.letzte_runde)}, beste {_zeit(auto.beste_runde)}{box}", f"P{platz} {_ki_name(auto)}, {abstand}, "
                     f"last {_zeit(auto.letzte_runde)}, best {_zeit(auto.beste_runde)}{box}"))

        # Wer fährt physisch auf der Strecke um ihn herum
        z.append(L("\nAUF DER STRECKE (wer physisch direkt vor und hinter ihm fährt)", "\nON TRACK (who is physically directly ahead of and behind him)"))
        for richtung, wort in (("vorne", L("vor ihm", "ahead of him")), ("hinten", L("hinter ihm", "behind him"))):
            auto, sekunden, runden = _sicher(ri.strecken_nachbar, stand, richtung) or (None, None, None)
            if auto is None:
                z.append(L(f"Direkt {wort}: niemand.", f"Directly {wort}: nobody."))
                continue
            platz = f"P{liste.index(auto) + 1}" if auto in liste else "?"
            beziehung = (L("gleiche Runde", "same lap") if runden == 0 else
                         L(f"{-runden} Runde(n) zurück (überrundet)", f"{-runden} lap(s) down (lapped)") if runden < 0 else
                         L(f"{runden} Runde(n) voraus", f"{runden} lap(s) up"))
            abstand = f"{ri.zahl(sekunden)} s" if sekunden is not None else "unbekannt"
            z.append(L(f"Direkt {wort}: {platz} {ri.name_von(auto)}, {abstand}, {beziehung}.", f"Directly {wort}: {platz} {ri.name_von(auto)}, {abstand}, {beziehung}."))
    else:
        z.append(L("\nKeine Verbindung zur Zeitnahme, keine Daten zu anderen Autos.", "\nNo connection to timing, no data on other cars."))
    # Auswertungen
    z.append(L("\nAUSWERTUNG", "\nANALYSIS"))
    z.append(L("Sektoren: ", "Sectors: ") + (_sicher(ri.antwort_sektoren, stand) or "unbekannt"))
    z.append(L("Konstanz: ", "Consistency: ") + (_sicher(ri.antwort_konstanz, stand) or "unbekannt"))
    z.append(L("Kurven (letzte Runde gegen Bestrunde): ", "Corners (last lap vs best lap): ") + (_sicher(ri.kurven_satz, stand) or L("keine Auffälligkeit", "nothing notable")))
    z.append(L("Boxenstopp: ", "Pit stop: ") + (_sicher(ri.antwort_rauskommen, stand) or "unbekannt"))
    if g.session == 2:
        z.append(L("Gegner an der Box: ", "Opponents in the pits: ") + (_sicher(ri.antwort_gegner_box, stand) or "unbekannt"))
    else:
        z.append(L("Bestzeit im Feld: ", "Best time in the field: ") + (_sicher(ri.antwort_pole, stand) or "unbekannt"))
    z.append(L("Reifenwahl: ", "Tyre choice: ") + (_sicher(ri.antwort_reifenwahl, stand) or "unbekannt"))
    z.append(L("Reifendruck nächster Stint: ", "Tyre pressure next stint: ") + (_sicher(ri.druck_text, stand) or L("noch keine Empfehlung", "no recommendation yet")))
    if g.session != 2 or g.runden_fertig == 0:
        z.append(L("Startsprit für das Rennen: ", "Start fuel for the race: ") + (_sicher(ri.startsprit_text, stand, None, True) or "unbekannt"))
    hinweis = _sicher(ri.zuspruch, stand, True)
    if hinweis:
        z.append(L(f"\nTAKTIK-HINWEIS: {hinweis}", f"\nTACTICAL HINT: {hinweis}"))
    return "\n".join(zeile for zeile in z if zeile)


# ---------------------------------------------------------------------------
# Gespräch mit der KI
# ---------------------------------------------------------------------------
SATZENDE = re.compile(r"(.+?[.!?])(\s+|$)", re.S)


def warnungen_finden(stand):
    """Echte Probleme am Auto, nach festen Grenzen. Nur das darf die KI von sich aus ansprechen."""
    p, g = stand.physik, stand.grafik
    w = []
    if p.wasser_temp > 112:
        w.append(L(f"Der Motor ist zu heiß ({p.wasser_temp:.0f} Grad Wasser).", f"The engine is too hot ({p.wasser_temp:.0f} degrees water)."))
    if any(x > 0.05 for x in p.schaden):
        w.append(L("Das Auto hat Schaden.", "The car is damaged."))
    belag = [b for b in p.belag if b > 0]
    if belag and min(belag) < 10:
        w.append(L(f"Die Bremsbeläge sind fast runter ({min(belag):.1f} mm).", f"The brake pads are almost worn out ({min(belag):.1f} mm)."))
    if g.strafe:
        w.append(L("Der Fahrer hat eine offene Strafe.", "The driver has an open penalty."))
    lage = ri.sprit_lage(stand)
    if lage and lage[2]["reicht_runden"] < 2:
        w.append(L("Der Sprit reicht nur noch für weniger als zwei Runden.", "Fuel only lasts for less than two laps."))
    return w


def hinweise_finden(stand):
    """Auswertungen nach festen Regeln, die ein Ingenieur ansprechen würde."""
    p, g = stand.physik, stand.grafik
    h = []
    regenreifen = "wet" in str(g.reifen_mischung).lower() or bool(g.regenreifen)
    warm = [t for t in p.reifen_kerntemp if t > 0]
    if not regenreifen and warm and min(warm) > 65 and g.runden_fertig >= 2 and not g.in_boxengasse:
        namen = ri.RAEDER
        zu_hoch = [namen[i] for i, d in enumerate(p.reifendruck) if d > 27.5]
        zu_tief = [namen[i] for i, d in enumerate(p.reifendruck) if 0 < d < 25.5]
        if zu_hoch:
            h.append(L(f"Reifendruck zu hoch ({', '.join(zu_hoch)}), ideal sind etwa 26 bis 27 PSI warm.", f"Tyre pressure too high ({', '.join(zu_hoch)}), ideal is about 26 to 27 PSI hot."))
        if zu_tief:
            h.append(L(f"Reifendruck zu niedrig ({', '.join(zu_tief)}), ideal sind etwa 26 bis 27 PSI warm.", f"Tyre pressure too low ({', '.join(zu_tief)}), ideal is about 26 to 27 PSI hot."))
    empfehlung = ri.regen_empfehlung(stand)
    if empfehlung:
        h.append(empfehlung)
    return h


class Gespraech:
    """Merkt sich die letzten Fragen und Antworten für Nachfragen.
    Nur kurz: Was vor über 90 Sekunden war, ist vergessen, damit sich die KI nicht in
    einem alten Thema festbeißt."""

    def __init__(self, laenge=2, haltbar=90):
        self.eintraege = deque(maxlen=laenge)
        self.haltbar = haltbar

    @property
    def verlauf(self):
        jetzt = time.monotonic()
        nachrichten = []
        for zeit, frage, antwort in self.eintraege:
            if jetzt - zeit <= self.haltbar:
                nachrichten += [{"role": "user", "content": frage},
                                {"role": "assistant", "content": antwort}]
        return nachrichten

    def merken(self, frage, antwort):
        self.eintraege.append((time.monotonic(), frage, antwort))


AUF_PROZESSOR = False   # True: KI rechnet auf dem Prozessor, die Grafikkarte bleibt frei für ACC
FAHRER_NAME = ""
INGENIEUR_NAME = "Fritz"


def namen_text():
    teile = []
    if ri.NAMEN_MODUS == "auto":
        teile.append(L("Nenne andere Fahrer NICHT beim Namen (die Stimme spricht fremde Namen schlecht aus), "
                     "sondern mit Auto und Platz, zum Beispiel: 'Der Ferrari auf Platz 5 ist 2 Minuten "
                     "18,4 Sekunden gefahren.' Ist die Marke unbekannt, sag 'das Auto auf Platz 5'.", "Do NOT call other drivers by their name (the voice pronounces foreign names badly), "
                     "but by car and position, for example: 'The Ferrari in P5 did a 2 minutes "
                     "18.4 seconds.' If the brand is unknown, say 'the car in P5'."))
    if INGENIEUR_NAME:
        teile.append(L(f"Dein Name ist {INGENIEUR_NAME}.", f"Your name is {INGENIEUR_NAME}."))
    if FAHRER_NAME:
        teile.append(L(f"Der Fahrer heißt {FAHRER_NAME}. Sprich ihn ab und zu mit seinem Namen an, "
                     f"aber nicht in jeder Antwort.", f"The driver's name is {FAHRER_NAME}. Address him by name now and then, "
                     f"but not in every answer."))
    return ("\n" + " ".join(teile) + "\n") if teile else ""


# Wo die KI läuft: "lokal" (Ollama auf deinem PC) oder online "gemini" / "groq" (kostenlos, mit API-Schlüssel)
ANBIETER = "lokal"
SCHLUESSEL = ""
AUSWEICH = []            # weitere (anbieter, schluessel), falls der erste überlastet ist
MELDEN = None            # Funktion für Hinweise ins Protokoll


def _stuecke(modell, nachrichten, zeitlimit):
    """Die Antwort der KI in kleinen Textstücken, egal ob lokal oder online."""
    if ANBIETER in ("gemini", "groq"):
        import acc_online
        yield from acc_online.chat_mit_ausweich([(ANBIETER, SCHLUESSEL)] + AUSWEICH, nachrichten,
                                                max_tokens=350, zeitlimit=zeitlimit, melden=MELDEN)
        return
    anfrage = {"model": modell, "messages": nachrichten, "stream": True, "keep_alive": "60m",
               "options": {"temperature": 0.3, "num_predict": 300, "num_ctx": 8192,
                           **({"num_gpu": 0} if AUF_PROZESSOR else {}),
                           "repeat_penalty": 1.15}}
    with _anfrage("/api/chat", anfrage, zeitlimit=zeitlimit) as antwort:
        for zeile in antwort:
            if not zeile.strip():
                continue
            stueck = json.loads(zeile)
            if "error" in stueck:
                raise RuntimeError(stueck["error"])
            yield stueck.get("message", {}).get("content", "")
            if stueck.get("done"):
                break


def antworten(modell, frage, daten, gespraech=None, zeitlimit=20.0, fakten=""):
    """Fragt die KI und liefert die Antwort Satz für Satz (Generator)."""
    nachrichten = [{"role": "system", "content": SYSTEM + namen_text()}]
    if gespraech:
        nachrichten += list(gespraech.verlauf)
    nachrichten.append({"role": "user",
                        "content": L(f"AKTUELLE DATEN:\n{daten}\n\n", f"CURRENT DATA:\n{daten}\n\n")
                                   + (L(f"PASSENDE FAKTEN:\n{fakten}\n\n", f"RELEVANT FACTS:\n{fakten}\n\n") if fakten else "")
                                   + L(f"DER FAHRER SAGT: \"{frage}\"", f"THE DRIVER SAYS: \"{frage}\"")})
    puffer = ""
    ganz = []
    for text in _stuecke(modell, nachrichten, zeitlimit):
        puffer += text
        # Fertige Sätze sofort weitergeben (mindestens 12 Zeichen, damit "P3." nicht allein kommt)
        while True:
            treffer = SATZENDE.match(puffer)
            if not treffer or len(treffer.group(1)) < 12 or not treffer.group(2):
                break
            satz = _aufraeumen(treffer.group(1))
            puffer = puffer[treffer.end():]
            if satz:
                ganz.append(satz)
                yield satz
    rest = _aufraeumen(puffer)
    if rest:
        ganz.append(rest)
        yield rest
    if gespraech is not None and ganz:
        gespraech.merken(frage, " ".join(ganz))


REDE_SYSTEM = L(
    "Du bist ein erfahrener, herzlicher Renningenieur am Boxenfunk (Sim-Racing, Assetto Corsa Competizione). "
    "Die Session ist gerade vorbei. Halte jetzt das Debriefing als EINEN Funkspruch, so wie ein echter Ingenieur nach dem Rennen: "
    "1. Ergebnis kurz einordnen. 2. Ehrlich loben, was gut war, mit konkreten Zahlen aus den Daten. "
    "3. Ein bis zwei konkrete Punkte, wo noch Zeit liegt, mit einem kurzen, praktischen Tipp. "
    "4. Ein motivierender Abschluss, und sag am Ende kurz, dass du jetzt ruhig bist, bis die nächste Session startet, "
    "und er dich jederzeit fragen kann. "
    "Regeln: 5 bis 8 Sätze, gesprochene Sprache, keine Listen, kein Markdown, keine Emojis. "
    "Benutze NUR die Fakten aus den Daten, erfinde nichts. Zeiten so schreiben, wie sie in den Daten stehen. "
    "Sag 'Abstand' statt 'Luft'. Erwähne nicht, wie er in die Box gekommen ist. Antworte auf Deutsch.",
    "You are an experienced, warm race engineer on the pit radio (sim racing, Assetto Corsa Competizione). "
    "The session has just ended. Give the debrief now as ONE radio message, like a real engineer after the race: "
    "1. Put the result into context briefly. 2. Honestly praise what went well, with concrete numbers from the data. "
    "3. One or two concrete points where there is still time to find, with a short practical tip. "
    "4. A motivating close, and say briefly at the end that you'll stay quiet until the next session starts "
    "and that he can ask you anything at any time. "
    "Rules: 5 to 8 sentences, spoken language, no lists, no markdown, no emojis. "
    "Use ONLY the facts from the data, invent nothing. Write times as they appear in the data. "
    "Do not mention how he got back to the pits. Answer in English.")


def debrief_rede(modell, fakten, zeitlimit=25.0):
    """Die Rede nach der Session von der KI. Gibt den fertigen Text zurück (oder wirft einen Fehler)."""
    nachrichten = [{"role": "system", "content": REDE_SYSTEM + namen_text()},
                   {"role": "user", "content": L("DATEN DER SESSION:\n", "SESSION DATA:\n") + fakten}]
    text = _aufraeumen("".join(_stuecke(modell, nachrichten, zeitlimit)))
    if len(text) < 60:
        raise RuntimeError(L("Die KI-Rede war zu kurz", "The AI speech was too short"))
    return text


BEGRUESSUNG = re.compile(r"^\s*(guten\s+(morgen|tag|abend|nachmittag)|hallo|hi|hey|servus|moin|grüß\s+dich|grüezi"
                         r"|good\s+(morning|afternoon|evening)|hello)\b[\s,!.]*", re.I)
FUELLWOERTER = re.compile(r"(^|(?<=[\s,]))(ähm+|äh+|öhm+|hmm+|hm|uhm+|um+|uh+|em+)[\s,.!]*(?=\s|$)", re.I)


LUFT = re.compile(r"\b(?:(?:genug|viel|wenig|etwas|mehr|weniger|keine|kaum|reichlich|bisschen|ordentlich) Luft"
                  r"|Luft nach (?:vorne|vorn|hinten)|Luft zu|Luft gewonnen|Luft verloren)\b")


def _aufraeumen(text):
    text = re.sub(r"[*_#`•]", "", text)            # falls doch Markdown kommt
    text = text.replace("…", ".").replace("...", ".")
    text = BEGRUESSUNG.sub("", text)               # kein "Guten Abend" vor jeder Antwort
    if FAHRER_NAME:                                 # "Lutz." oder "Lutz!" allein übrig?
        text = re.sub(rf"^\s*{re.escape(FAHRER_NAME)}\s*[,!.]\s*", "", text) if len(text) < len(FAHRER_NAME) + 4 else text
    text = FUELLWOERTER.sub(" ", text)             # kein "Ähm" und "Hmm"
    text = LUFT.sub(lambda m: m.group(0).replace("Luft", "Abstand"), text)   # "genug Luft" -> "genug Abstand"
    text = re.sub(r"\s+", " ", text).strip()
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return "" if re.fullmatch(r"[\W_]*", text) else text
