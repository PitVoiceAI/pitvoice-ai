// Renningenieur – Oberfläche
// Holt mehrmals pro Sekunde neue Daten vom Python-Teil (window.pywebview.api) und zeigt sie an.

"use strict";

const api = () => window.pywebview.api;
let D = null;            // alles vom Start (Listen, Einstellungen)
let E = {};              // Einstellungen
let zustand = "aus";
let feld = { autos: [], karte: [] };
let fokus = null;        // Index des Autos im Fokus, null = du
let fokusSignatur = null;
let aktuelleSession = null;
let funkEintraege = [];
let seite = "cockpit";
let SPRACHE = "de";      // "de" oder "en", kommt beim Start aus Python

// Deutsch oder Englisch: T("Deutsch", "English")
const T = (de, en) => (SPRACHE === "en" ? en : de);

// ---------------------------------------------------------------- Hilfen
const $ = (id) => document.getElementById(id);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (z) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[z]));
const komma = (x, n = 1) => (x == null || isNaN(x) ? "–" : Number(x).toFixed(n).replace(".", T(",", ".")));
function zeit(ms) {
  if (!ms || ms <= 0) return "–";
  const m = Math.floor(ms / 60000);
  const s = (ms - m * 60000) / 1000;
  return `${m}:${s.toFixed(3).padStart(6, "0").replace(".", T(",", "."))}`;
}
const uhr = () => new Date().toLocaleTimeString(T("de-DE", "en-GB"), { hour: "2-digit", minute: "2-digit" });
const ingName = () => E.ingenieur_name || T("Ingenieur", "Engineer");

function toast(text, fehler = false) {
  const t = document.createElement("div");
  t.className = "toast glas" + (fehler ? " fehler" : "");
  t.textContent = text;
  $("toasts").appendChild(t);
  setTimeout(() => t.remove(), fehler ? 9000 : 5000);
}

let speicherTimer = null;
function speichern(teil, sofort = true) {
  Object.assign(E, teil);
  clearTimeout(speicherTimer);
  const los = async () => {
    const r = await api().speichern(teil);
    const h = $("einstellung-hinweis");
    h.textContent = r && r.gilt_ab_start ? T("Gespeichert. Gilt ab dem nächsten Start.", "Saved. Applies from the next start.") : T("Gespeichert", "Saved");
    h.className = "unter " + (r && r.gilt_ab_start ? "gelb" : "gruen");
    setTimeout(() => { h.textContent = T("Wird automatisch gespeichert", "Saved automatically"); h.className = "unter"; }, 3000);
  };
  if (sofort) los(); else speicherTimer = setTimeout(los, 400);
}

function segment(el, werte, aktuell, beiWahl, anzeige = (w) => w) {
  el.innerHTML = "";
  for (const w of werte) {
    const b = document.createElement("button");
    b.textContent = anzeige(w);
    b.setAttribute("aria-pressed", String(w === aktuell));
    if (w === aktuell) b.classList.add("an");
    b.onclick = () => {
      [...el.children].forEach((k) => { k.classList.remove("an"); k.setAttribute("aria-pressed", "false"); });
      b.classList.add("an"); b.setAttribute("aria-pressed", "true");
      beiWahl(w);
    };
    el.appendChild(b);
  }
}

function optionen(el, liste, aktuell) {
  el.innerHTML = liste.map(([wert, text]) => `<option value="${esc(wert)}"${wert === aktuell ? " selected" : ""}>${esc(text)}</option>`).join("");
}

// ---------------------------------------------------------------- Navigation
function zeigen(ziel) {
  seite = ziel;
  document.querySelectorAll(".seite").forEach((s) => s.classList.toggle("versteckt", s.dataset.seite !== ziel));
  document.querySelectorAll(".nav-knopf").forEach((k) => k.classList.toggle("aktiv", k.dataset.ziel === ziel));
  if (ziel === "live") liveZeigen();
  if (ziel === "funk") $("funk-verlauf").scrollTop = 1e9;
  if (ziel === "auswertung") sessionsAktualisieren();
  if (ziel === "fortschritt") fortschrittLaden();
}
document.querySelectorAll(".nav-knopf").forEach((k) => (k.onclick = () => zeigen(k.dataset.ziel)));

// ---------------------------------------------------------------- Start / Stopp
function zustandSetzen(z, text) {
  zustand = z;
  $("punkt").className = "punkt " + z;
  $("zustand-text").textContent = text || { aus: T("Gestoppt", "Stopped"), laedt: T("Starte ...", "Starting ..."), bereit: T("Bereit", "Ready"), stoppt: T("Stoppe ...", "Stopping ...") }[z];
  const k = $("start-knopf");
  k.disabled = z === "stoppt";
  k.textContent = z === "aus" ? T("Starten", "Start") : T("Stoppen", "Stop");
  k.classList.toggle("laeuft", z !== "aus");
  if (z === "aus") {
    $("funk-anzeige").textContent = "";
    cockpitLeer(T("Starte den Ingenieur unten links.", "Start the engineer at the bottom left."));
  }
}
$("start-knopf").onclick = async () => { zustandSetzen(await api().start_stopp()); };

// ---------------------------------------------------------------- Cockpit
function cockpitLeer(text) {
  $("pb-platz").textContent = "–"; $("pb-gesamt").textContent = "";
  for (const id of ["pb-vorne-wert", "pb-hinten-wert", "pb-hinten-name", "pb-runde", "pb-letzte", "pb-beste", "pb-strecke"]) $(id).textContent = "";
  $("pb-vorne-name").textContent = text;
  for (const id of ["st-tank", "st-box", "st-rest"]) $(id).textContent = "–";
  for (const id of ["st-tank-d", "st-box-d", "st-rest-d"]) $(id).textContent = "";
  $("st-balken").firstElementChild.style.width = "0%";
  $("cockpit-unter").textContent = T("Wartet auf eine Session", "Waiting for a session");
}

function cockpitZeigen(d) {
  if (!d.acc) { cockpitLeer(T("Warte auf ACC. Fahr auf die Strecke.", "Waiting for ACC. Drive onto the track.")); return; }
  $("cockpit-unter").textContent = T(`${d.session} in ${d.strecke}`, `${d.session} at ${d.strecke}`);
  $("pb-platz").textContent = d.platz ? `P${d.platz}` : "–";
  $("pb-gesamt").textContent = d.gesamt ? `/ ${d.gesamt}` : "";
  for (const s of ["vorne", "hinten"]) {
    const w = $(`pb-${s}-wert`), n = $(`pb-${s}-name`);
    const info = d[s];
    w.className = "wert";
    if (info) { w.textContent = info[2]; n.textContent = `P${info[0]} ${info[1]}`; }
    else if (s === "vorne" && d.platz === 1) { w.textContent = T("Führung", "Leading"); w.className = "wert gruen"; n.textContent = ""; }
    else if (s === "vorne" && !d.zeitnahme) { w.textContent = ""; n.textContent = T("Keine Verbindung zur Zeitnahme (broadcasting.json?)", "No connection to timing (broadcasting.json?)"); }
    else { w.textContent = ""; n.textContent = ""; }
  }
  $("pb-runde").textContent = `${T("Runde", "Lap")} ${d.runde}${d.runden_gesamt ? T(" von ", " of ") + d.runden_gesamt : ""}`;
  $("pb-letzte").innerHTML = `${T("Letzte", "Last")} <span class="zahl">${esc(d.letzte)}</span>`;
  $("pb-beste").innerHTML = `${T("Beste", "Best")} <span class="zahl">${esc(d.beste)}</span>`;
  const teile = [];
  for (const [s, wort] of [["strecke_vorne", T("vor dir", "ahead")], ["strecke_hinten", T("hinter dir", "behind")]]) {
    if (d[s]) { const [name, ab, r] = d[s]; teile.push(`${wort} ${name} ${ab}${r ? ` (${r > 0 ? "+" : ""}${r} ${T("Runde", "lap")})` : ""}`); }
  }
  $("pb-strecke").textContent = teile.length ? T("Auf der Strecke: ", "On track: ") + teile.join(", ") : "";
  $("st-tank").textContent = `${komma(d.tank)} L`;
  $("st-tank-d").textContent = d.reicht ? T(`reicht ${komma(d.reicht)} Runden`, `lasts ${komma(d.reicht)} laps`) : T("Verbrauch wird gemessen", "Measuring consumption");
  $("st-balken").firstElementChild.style.width = `${Math.max(0, Math.min(100, (d.tank / d.tank_max) * 100))}%`;
  $("st-balken").classList.toggle("knapp", (d.reicht ?? 99) < 2);
  $("st-box").textContent = d.box || "–";
  $("st-box").className = "wert" + (d.box === "Kein Stopp nötig" || d.box === "No stop needed" ? " gruen" : "");
  $("st-box-d").textContent = d.box_detail || T("nach einer vollen Runde", "after one full lap");
  $("st-rest").textContent = d.rest || "–";
  $("st-rest-d").textContent = d.rest_runden && !d.runden_gesamt ? T(`etwa ${Math.round(d.rest_runden)} Runden`, `about ${Math.round(d.rest_runden)} laps`) : "";
}

// ---------------------------------------------------------------- Funk
function blaseHtml(art, text, zeitpunkt) {
  if (["system", "fehler", "zeit"].includes(art)) return `<div class="systemzeile${art === "fehler" ? " fehler" : ""}">${esc(text)} · ${zeitpunkt}</div>`;
  const wer = art === "du" ? T("Du", "You") : art === "ansage" ? `${ingName()}, ${T("von selbst", "unprompted")}` : ingName();
  return `<div class="blase ${art}"><div class="wer">${esc(wer)} · ${zeitpunkt}</div>${esc(text)}</div>`;
}
function funkEintrag(art, text) {
  const e = { art, text, zeit: uhr() };
  funkEintraege.push(e);
  if (funkEintraege.length > 300) funkEintraege.shift();
  const v = $("funk-verlauf");
  const unten = v.scrollHeight - v.scrollTop - v.clientHeight < 60;
  v.insertAdjacentHTML("beforeend", blaseHtml(e.art, e.text, e.zeit));
  while (v.children.length > 300) v.firstElementChild.remove();
  if (unten || seite !== "funk") v.scrollTop = 1e9;
  const wichtige = funkEintraege.filter((f) => !["system", "zeit"].includes(f.art)).slice(-4);
  $("kurzfunk").innerHTML = wichtige.length ? wichtige.map((f) => blaseHtml(f.art, f.text, f.zeit)).join("")
    : `<div class="leise">${T("Noch kein Funk. Halte die Funktaste und frag zum Beispiel nach dem Sprit.", "No radio yet. Hold the radio button and ask about fuel, for example.")}</div>`;
}

// ---------------------------------------------------------------- Live-Karte
function fokusAuto() {
  return feld.autos.find((a) => (fokus === null ? a.ich : a.index === fokus)) || null;
}

function liveZeigen() {
  ranglisteZeigen();
  karteZeichnen();
  fokusZeigen();
  $("live-unter").textContent = feld.autos.length
    ? T("Klick auf einen Fahrer in der Liste oder auf der Karte, um seine Runden und Sektoren zu sehen.", "Click a driver in the list or on the map to see his laps and sectors.")
    : T("Noch keine Daten. Starte den Ingenieur und fahr auf die Strecke.", "No data yet. Start the engineer and drive onto the track.");
}

function ranglisteZeigen() {
  const f = fokusAuto();
  $("rangliste").innerHTML = feld.autos.map((a) => {
    const klassen = ["zeile-knopf", a.ich ? "ich" : "", f && a.index === f.index && !a.ich ? "fokus" : "", a.box ? "box" : ""].join(" ");
    const nummer = a.nummer != null ? `#${a.nummer} ` : "";
    return `<button class="${klassen}" data-index="${a.index}"><span class="pl">P${a.platz}</span><span class="nm">${esc(nummer + a.fahrer)}${a.box ? T(" · Box", " · Pits") : ""}</span><span class="ab">${a.ich ? T("Du", "You") : esc(a.abstand)}</span></button>`;
  }).join("") || `<div class="leer-hinweis">${T("Keine Fahrer. Die Zeitnahme muss verbunden sein.", "No drivers. Timing has to be connected.")}</div>`;
  $("rangliste").querySelectorAll(".zeile-knopf").forEach((b) => (b.onclick = () => fokusSetzen(Number(b.dataset.index))));
}

function fokusSetzen(index) {
  const a = feld.autos.find((x) => x.index === index);
  fokus = a && a.ich ? null : index;
  fokusSignatur = null;
  liveZeigen();
}

let kartenRahmen = null;
function karteZeichnen() {
  const svg = $("karte");
  const punkte = feld.karte || [];
  const autos = feld.autos.filter((a) => a.x != null);
  const alle = punkte.concat(autos.map((a) => [a.x, a.y]));
  $("karte-leer").classList.toggle("versteckt", alle.length >= 2);
  if (alle.length < 2) { svg.innerHTML = ""; return; }
  const spiegel = E.karte_spiegeln ? -1 : 1;
  const xs = alle.map((p) => p[0]), ys = alle.map((p) => p[1] * spiegel);
  let [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const rand = Math.max(maxX - minX, maxY - minY) * 0.06 + 1;
  // Den Rahmen nur ändern, wenn sich die Strecke deutlich ändert, damit nichts zappelt
  const neu = [minX - rand, minY - rand, maxX - minX + 2 * rand, maxY - minY + 2 * rand];
  if (!kartenRahmen || neu.some((w, i) => Math.abs(w - kartenRahmen[i]) > rand * 0.5)) kartenRahmen = neu;
  svg.setAttribute("viewBox", kartenRahmen.join(" "));
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  const groesse = Math.max(kartenRahmen[2], kartenRahmen[3]);
  const r = groesse * 0.016;

  let strecke = svg.querySelector("#strecke");
  if (!strecke) {
    svg.innerHTML = `<defs><filter id="leuchten" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="${r * 0.7}"></feGaussianBlur></filter></defs>
      <g id="strecke"></g><g id="autos"></g>`;
    strecke = svg.querySelector("#strecke");
  }
  if (punkte.length > 2) {
    const d = "M" + punkte.map((p) => `${p[0].toFixed(1)} ${(p[1] * spiegel).toFixed(1)}`).join(" L") + " Z";
    const sx = punkte[0][0], sy = punkte[0][1] * spiegel;
    strecke.innerHTML = `<path d="${d}" fill="none" stroke="rgba(255,255,255,0.07)" stroke-width="${r * 2.2}" stroke-linejoin="round"></path>
      <path d="${d}" fill="none" stroke="rgba(255,255,255,0.30)" stroke-width="${r * 0.28}" stroke-linejoin="round"></path>
      <circle cx="${sx}" cy="${sy}" r="${r * 0.55}" fill="#fff"></circle>`;
  } else strecke.innerHTML = "";

  const gruppe = svg.querySelector("#autos");
  const f = fokusAuto();
  const vorhanden = new Map([...gruppe.children].map((g) => [Number(g.dataset.index), g]));
  // Reihenfolge: du und der Fokus ganz oben
  const sortiert = [...autos].sort((a, b) => (a.ich - b.ich) || ((f && a.index === f.index) - (f && b.index === f.index)));
  for (const a of sortiert) {
    let g = vorhanden.get(a.index);
    vorhanden.delete(a.index);
    const istFokus = f && a.index === f.index;
    const farbe = a.ich ? "#FFC83D" : istFokus ? "#B57BFF" : a.box ? "rgba(255,255,255,0.28)" : "#F2F3F5";
    const textFarbe = a.box && !a.ich && !istFokus ? "#E6E8EC" : "#111";
    const rr = a.ich ? r * 1.15 : r;
    const inhalt = `${a.ich || istFokus ? `<circle r="${rr * 1.5}" fill="${farbe}" opacity="0.55" filter="url(#leuchten)"></circle>` : ""}
      ${istFokus ? `<circle r="${rr * 1.55}" fill="none" stroke="#B57BFF" stroke-width="${r * 0.16}"></circle>` : ""}
      <circle r="${rr}" fill="${farbe}" stroke="#050506" stroke-width="${r * 0.15}"></circle>
      <text y="${rr * 0.36}" text-anchor="middle" font-size="${rr * 1.0}" fill="${textFarbe}">${a.platz}</text>`;
    if (!g) {
      g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", "auto");
      g.dataset.index = a.index;
      g.onclick = () => fokusSetzen(a.index);
      g.style.transform = `translate(${a.x}px, ${a.y * spiegel}px)`;
      gruppe.appendChild(g);
    }
    if (g.dataset.inhalt !== inhalt) { g.innerHTML = inhalt; g.dataset.inhalt = inhalt; }
    // Große Sprünge (Box, Neustart) nicht animieren
    const alt = g.dataset.pos ? g.dataset.pos.split(",").map(Number) : null;
    const sprung = alt && Math.hypot(alt[0] - a.x, alt[1] - a.y * spiegel) > groesse * 0.25;
    g.style.transition = sprung ? "none" : "";
    g.style.transform = `translate(${a.x}px, ${a.y * spiegel}px)`;
    g.dataset.pos = `${a.x},${a.y * spiegel}`;
    gruppe.appendChild(g);   // Reihenfolge = Zeichenreihenfolge
  }
  vorhanden.forEach((g) => g.remove());
}

async function fokusZeigen() {
  const a = fokusAuto();
  const kopf = $("fokus-kopf"), box = $("fokus-tabelle");
  if (!a) { kopf.innerHTML = `<span class="leise">${T("Kein Fahrer ausgewählt", "No driver selected")}</span>`; box.innerHTML = ""; fokusSignatur = null; return; }
  const wer = a.ich ? T("Du", "You") : a.fahrer;
  kopf.innerHTML = `<span class="pl ${a.ich ? "ich-pl" : ""}">P${a.platz}</span><span class="nm">${esc(wer)}</span>
    <span class="leise">${a.abstand ? T("Abstand ", "Gap ") + esc(a.abstand) + (/[RL]$/.test(a.abstand) ? "" : " s") + " · " : ""}${T("Beste", "Best")} <span class="zahl lila">${zeit(a.beste)}</span> · ${a.stopps} ${a.stopps === 1 ? T("Stopp", "stop") : T("Stopps", "stops")}</span>`;
  const signatur = `${a.index}|${a.rundenzahl}|${a.beste}`;
  if (signatur === fokusSignatur) return;
  fokusSignatur = signatur;
  const runden = (await api().runden(a.index)) || [];
  if (fokusSignatur !== signatur) return;
  if (!runden.length) { box.innerHTML = `<div class="leer-hinweis">${T("Noch keine fertige Runde gesehen.", "No completed lap seen yet.")}</div>`; return; }
  box.innerHTML = rundenTabelle(runden.map((r) => ({ nummer: r.runde, zeit: r.zeit, sektoren: r.sektoren, gueltig: r.gueltig, box: r.box })), false);
}

function bestwerte(runden) {
  const gueltig = runden.filter((r) => r.gueltig);
  const beste = gueltig.length ? Math.min(...gueltig.map((r) => r.zeit)) : null;
  const sek = [];
  for (const r of gueltig) (r.sektoren || []).forEach((z, i) => { if (z && (sek[i] == null || z < sek[i])) sek[i] = z; });
  return [beste, sek];
}

function rundenTabelle(runden, erweitert) {
  const [beste, sek] = bestwerte(runden);
  const kopf = `<tr><th>${T("Runde", "Lap")}</th><th>${T("Zeit", "Time")}</th>${erweitert ? `<th>${T("Abstand", "Gap")}</th>` : ""}<th>${T("Sektor", "Sector")} 1</th><th>${T("Sektor", "Sector")} 2</th><th>${T("Sektor", "Sector")} 3</th>${erweitert ? `<th>${T("Platz", "Pos")}</th><th>Tank</th>` : ""}</tr>`;
  const zeilen = [...runden].reverse().map((r) => {
    const klasse = !r.gueltig ? "ungueltig" : r.box ? "box" : "";
    const zusatz = r.box ? T(" Box", " pit") : !r.gueltig ? T(" ungültig", " invalid") : "";
    const istBeste = r.gueltig && r.zeit === beste;
    const s = [0, 1, 2].map((i) => {
      const z = (r.sektoren || [])[i];
      return `<td class="${r.gueltig && z && z === sek[i] ? "beste" : ""}">${z ? komma(z / 1000, 3) : "–"}</td>`;
    }).join("");
    const extra = erweitert ? `<td>${beste && !istBeste ? "+" + komma((r.zeit - beste) / 1000, 3) : ""}</td>` : "";
    const ende = erweitert ? `<td>${r.platz ? "P" + r.platz : "–"}</td><td>${r.tank != null ? komma(r.tank) + " L" : "–"}</td>` : "";
    return `<tr class="${klasse}"><td>${r.nummer}</td><td class="${istBeste ? "beste" : ""}">${zeit(r.zeit)}${zusatz}</td>${extra}${s}${ende}</tr>`;
  }).join("");
  return `<table>${kopf}${zeilen}</table>`;
}

$("karte-spiegeln").onclick = () => { speichern({ karte_spiegeln: !E.karte_spiegeln }); kartenRahmen = null; $("karte").innerHTML = ""; karteZeichnen(); };

// ---------------------------------------------------------------- Auswertung
async function sessionsAktualisieren() {
  const dateien = (await api().sessions()) || [];
  const el = $("session-auswahl");
  const gewaehlt = el.value || "aktuell";
  el.innerHTML = `<option value="aktuell">${T("Aktuelle Session", "Current session")}</option>` +
    dateien.map((d) => `<option value="${esc(d)}">${esc(d.replace(".json", "").replaceAll("_", "  "))}</option>`).join("");
  el.value = [...el.options].some((o) => o.value === gewaehlt) ? gewaehlt : "aktuell";
}
$("session-auswahl").onchange = async (ev) => {
  if (ev.target.value === "aktuell") auswertungZeigen(aktuelleSession);
  else auswertungZeigen(await api().session_laden(ev.target.value));
};
$("ordner-oeffnen").onclick = () => api().ordner_oeffnen();

function auswertungZeigen(d) {
  const runden = d && d.runden ? d.runden : [];
  teleLaden(d);
  if (!runden.length) {
    for (const id of ["k-bestzeit", "k-runden", "k-konstanz", "k-trend", "k-platz", "k-stopps"]) $(id).textContent = "–";
    $("auswertung-tabelle").innerHTML = `<div class="leer-hinweis">${T("Noch keine Runden. Sobald du fährst, erscheinen sie hier. Nach jeder Session wird alles im Ordner „rennen“ gespeichert.", "No laps yet. As soon as you drive, they appear here. After every session everything is saved in the “rennen” folder.")}</div>`;
    $("diagramm").innerHTML = "";
    return;
  }
  const datum = new Date((d.beginn || Date.now() / 1000) * 1000).toLocaleString(T("de-DE", "en-GB"), { dateStyle: "medium", timeStyle: "short" });
  $("auswertung-unter").textContent = `${d.session || ""} ${T("in", "at")} ${streckenName(d.strecke)}, ${datum}`;
  $("k-bestzeit").textContent = zeit(d.bestzeit);
  $("k-runden").textContent = runden.length;
  $("k-konstanz").textContent = d.konstanz != null ? `±${komma(d.konstanz / 2, 2)} s` : "–";
  const tr = $("k-trend");
  tr.textContent = d.trend != null ? `${d.trend > 0 ? "+" : ""}${komma(d.trend, 2)} s` : "–";
  tr.className = "wert" + (d.trend > 0.15 ? " rot" : d.trend != null && d.trend < 0 ? " gruen" : "");
  const letzterPlatz = [...runden].reverse().find((r) => r.platz)?.platz;
  $("k-platz").textContent = `P${d.startplatz || "–"} → ${d.aufgegeben ? T("Aufgegeben", "Retired") : "P" + (d.endplatz || letzterPlatz || "–")}`;
  $("k-stopps").textContent = `${d.stopps || 0} / ${d.strafen || 0}`;
  $("auswertung-tabelle").innerHTML = rundenTabelle(runden, true);
  diagrammZeichnen(runden, d.bestzeit);
}

function diagrammZeichnen(runden, beste) {
  const svg = $("diagramm");
  const b = svg.clientWidth || 900, h = svg.clientHeight || 220;
  const links = 70, rechts = 16, oben = 22, unten = 26;
  const sauber = runden.filter((r) => r.gueltig && !r.box).map((r) => r.zeit);
  const werte = sauber.length ? sauber : runden.map((r) => r.zeit);
  const sortiert = [...werte].sort((a, c) => a - c);
  let lo = sortiert[0], hi = Math.max(sortiert[Math.floor(sortiert.length * 0.9)] ?? lo, lo + 1000);
  hi += (hi - lo) * 0.15; lo -= (hi - lo) * 0.1;
  const y = (z) => oben + (Math.min(Math.max(z, lo), hi) - lo) / (hi - lo) * (h - oben - unten);
  const x = (i) => runden.length === 1 ? (links + b - rechts) / 2 : links + i / (runden.length - 1) * (b - links - rechts);
  let s = "";
  for (let k = 0; k < 5; k++) {
    const w = lo + (hi - lo) * k / 4;
    s += `<line x1="${links}" x2="${b - rechts}" y1="${y(w)}" y2="${y(w)}" stroke="rgba(255,255,255,0.07)"></line>
      <text x="${links - 8}" y="${y(w) + 4}" text-anchor="end" font-size="11" fill="#7D828C" font-family="Bahnschrift, sans-serif">${zeit(w)}</text>`;
  }
  const schritt = Math.max(1, Math.floor(runden.length / 14));
  runden.forEach((r, i) => { if (i % schritt === 0 || i === runden.length - 1) s += `<text x="${x(i)}" y="${h - 6}" text-anchor="middle" font-size="11" fill="#7D828C" font-family="Bahnschrift, sans-serif">${r.nummer}</text>`; });
  const linie = runden.map((r, i) => (r.gueltig && !r.box ? `${x(i)},${y(r.zeit)}` : null)).filter(Boolean);
  if (linie.length > 1) {
    s += `<defs><linearGradient id="flaeche" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#FFC83D" stop-opacity="0.22"></stop><stop offset="1" stop-color="#FFC83D" stop-opacity="0"></stop></linearGradient></defs>`;
    const ersterX = linie[0].split(",")[0], letzterX = linie[linie.length - 1].split(",")[0];
    s += `<polygon points="${ersterX},${h - unten} ${linie.join(" ")} ${letzterX},${h - unten}" fill="url(#flaeche)"></polygon>`;
    s += `<polyline points="${linie.join(" ")}" fill="none" stroke="#FFC83D" stroke-width="2.2" stroke-linejoin="round" style="filter:drop-shadow(0 0 6px rgba(255,200,61,0.6))"></polyline>`;
  }
  runden.forEach((r, i) => {
    const istBeste = r.gueltig && r.zeit === beste;
    const farbe = istBeste ? "#B57BFF" : !r.gueltig ? "#FF7A6E" : r.box ? "#7D828C" : "#FFC83D";
    s += `<circle cx="${x(i)}" cy="${y(r.zeit)}" r="${istBeste ? 6 : 3.5}" fill="${farbe}"${istBeste ? ' style="filter:drop-shadow(0 0 8px #B57BFF)"' : ""}></circle>`;
  });
  [[T("Bestzeit", "Best lap"), "#B57BFF"], [T("ungültig", "invalid"), "#FF7A6E"], [T("mit Box", "pit lap"), "#7D828C"]].forEach(([t, f], k) => {
    const px = b - rechts - 250 + k * 86;
    s += `<circle cx="${px}" cy="10" r="4" fill="${f}"></circle><text x="${px + 9}" y="14" font-size="11" fill="#9EA3AD">${t}</text>`;
  });
  svg.setAttribute("viewBox", `0 0 ${b} ${h}`);
  svg.innerHTML = s;
}
// ---------------------------------------------------------------- Fortschritt
let fortschrittDaten = {}, fortschrittWahl = null;
const streckenName = (s) => String(s || "").replaceAll("_", " ").replace(/\b\w/g, (z) => z.toUpperCase());
async function fortschrittLaden() {
  fortschrittDaten = (await api().fortschritt()) || {};
  const eintraege = Object.entries(fortschrittDaten).filter(([, e]) => (e.bestzeiten || []).length)
    .sort((a, b) => (b[1].zuletzt || 0) - (a[1].zuletzt || 0));
  if (!eintraege.length) {
    $("fortschritt-liste").innerHTML = `<div class="leise">${T("Noch keine Daten. Ab jetzt merkt sich dein Ingenieur bei jeder Session deine Bestzeit pro Strecke und Auto.", "No data yet. From now on your engineer remembers your best time per track and car in every session.")}</div>`;
    return;
  }
  if (!fortschrittWahl || !fortschrittDaten[fortschrittWahl]) fortschrittWahl = eintraege[0][0];
  $("fortschritt-liste").innerHTML = eintraege.map(([k, e]) => {
    const zeiten = e.bestzeiten.map((b) => b.zeit);
    const beste = Math.min(...zeiten), erste = zeiten[0];
    const besser = erste - beste;
    return `<button class="strecken-karte${k === fortschrittWahl ? " aktiv" : ""}" data-k="${esc(k)}"><span class="s">${esc(streckenName(e.strecke))}</span><span class="a">${esc(streckenName(e.auto))}</span>
      <span class="b">${zeit(beste)}</span><span class="d">${e.bestzeiten.length} Sessions${besser > 0 ? ` · ${komma(besser / 1000, 2)} ${T("s schneller als am Anfang", "s faster than at the start")}` : ""}</span></button>`;
  }).join("");
  $("fortschritt-liste").querySelectorAll(".strecken-karte").forEach((b) => (b.onclick = () => { fortschrittWahl = b.dataset.k; fortschrittLaden(); }));
  fortschrittZeichnen(fortschrittDaten[fortschrittWahl]);
}
function fortschrittZeichnen(e) {
  const svg = $("fortschritt-svg");
  $("fortschritt-titel").textContent = `${streckenName(e.strecke)} · ${streckenName(e.auto)}`;
  const info = [];
  if (e.rundenzeit) info.push(`${T("typische Runde", "typical lap")} ${zeit(e.rundenzeit * 1000)}`);
  if (e.verbrauch) info.push(`${komma(e.verbrauch, 2)} ${T("L pro Runde", "L per lap")}`);
  $("fortschritt-info").textContent = info.join(" · ");
  const punkte = e.bestzeiten;
  const b = svg.clientWidth || 900, h = svg.clientHeight || 260, links = 74, rechts = 20, oben = 18, unten = 34;
  const zeiten = punkte.map((p) => p.zeit);
  let lo = Math.min(...zeiten), hi = Math.max(...zeiten);
  const pad = Math.max(300, (hi - lo) * 0.15); lo -= pad; hi += pad;
  const x = (i) => punkte.length === 1 ? (links + b - rechts) / 2 : links + i / (punkte.length - 1) * (b - links - rechts);
  const y = (z) => oben + (z - lo) / (hi - lo) * (h - oben - unten);
  let s = "";
  for (let k = 0; k < 4; k++) { const w = lo + (hi - lo) * k / 3; s += `<line x1="${links}" x2="${b - rechts}" y1="${y(w)}" y2="${y(w)}" stroke="rgba(255,255,255,0.07)"></line><text x="${links - 8}" y="${y(w) + 4}" text-anchor="end" font-size="11" fill="#7D828C">${zeit(w)}</text>`; }
  const beste = Math.min(...zeiten);
  s += `<polyline points="${punkte.map((p, i) => `${x(i)},${y(p.zeit)}`).join(" ")}" fill="none" stroke="#FFC83D" stroke-width="2.2" style="filter:drop-shadow(0 0 6px rgba(255,200,61,0.55))"></polyline>`;
  punkte.forEach((p, i) => {
    const istBeste = p.zeit === beste;
    s += `<circle cx="${x(i)}" cy="${y(p.zeit)}" r="${istBeste ? 6 : 4}" fill="${istBeste ? "#B57BFF" : "#FFC83D"}"></circle>`;
    const datum = SPRACHE === "en" ? p.tag.split("-").reverse().slice(0, 2).join("/") : p.tag.split("-").reverse().slice(0, 2).join(".");
    if (punkte.length <= 14 || i % Math.ceil(punkte.length / 14) === 0) s += `<text x="${x(i)}" y="${h - 12}" text-anchor="middle" font-size="11" fill="#7D828C">${datum} ${p.session[0]}</text>`;
  });
  svg.setAttribute("viewBox", `0 0 ${b} ${h}`);
  svg.innerHTML = s;
}

// ---------------------------------------------------------------- Telemetrie
let tele = null;          // {laenge, beste, runden: {nr: {tempo, gas, bremse, zeit, gueltig, box, zeit_ms}}}
let teleQuelle = null;

async function teleLaden(d) {
  const aktuell = $("session-auswahl").value === "aktuell" || !$("session-auswahl").value;
  if (d && d.telemetrie) tele = d.telemetrie;
  else if (aktuell) tele = await api().telemetrie();
  else tele = null;
  teleFuellen();
}

function teleFuellen() {
  teleModusZeigen();
  const r = $("tele-runde"), v = $("tele-vergleich");
  const nummern = tele && tele.runden ? Object.keys(tele.runden).map(Number).sort((a, b) => b - a) : [];
  if (!nummern.length) {
    r.innerHTML = v.innerHTML = "";
    $("tele-svg").innerHTML = `<text x="20" y="40" fill="#9EA3AD" font-size="14">${T("Noch keine Telemetrie. Sie wird ab jetzt bei jeder vollständigen Runde aufgezeichnet.", "No telemetry yet. From now on it is recorded on every complete lap.")}</text>`;
    $("tele-kurven").innerHTML = "";
    return;
  }
  const text = teleRundeText;
  const alteR = Number(r.value), alteV = Number(v.value);
  r.innerHTML = nummern.map((nr) => `<option value="${nr}">${esc(text(nr))}</option>`).join("");
  v.innerHTML = nummern.map((nr) => `<option value="${nr}">${esc(text(nr))}</option>`).join("");
  const standard = nummern.find((nr) => nr !== tele.beste && tele.runden[nr].gueltig && !tele.runden[nr].box) ?? nummern[0];
  r.value = nummern.includes(alteR) ? alteR : standard;
  v.value = nummern.includes(alteV) ? alteV : (tele.beste ?? nummern[nummern.length - 1]);
  teleZeichnen();
}
$("tele-runde").onchange = () => teleZeichnen();
$("tele-vergleich").onchange = () => teleZeichnen();

// Farben: jede Messgröße hat EINE feste Farbe (Tempo gelb, Gas grün, Bremse rot).
// Beim Vergleich ist die gewählte Runde durchgezogen, die Vergleichsrunde gestrichelt.
const TELE = { tempo: "#FFC83D", gas: "#3DDC84", bremse: "#FF5A4E", gut: "#3DDC84", schlecht: "#FF7A6E", raster: "rgba(255,255,255,0.06)", text: "#8A909B" };
let teleAktuell = null;   // für die Maus-Anzeige
let teleModus = "eine";   // "eine" = nur eine Runde, "vergleich" = zwei Runden übereinander

function teleModusZeigen() {
  segment($("tele-modus"), ["eine", "vergleich"], teleModus, (w) => { teleModus = w; teleModusZeigen(); teleZeichnen(); },
    (w) => (w === "eine" ? T("Eine Runde", "Single lap") : T("Runden vergleichen", "Compare laps")));
  document.querySelectorAll(".tele-gegen").forEach((e) => (e.hidden = teleModus !== "vergleich"));
}
teleModusZeigen();

function teleRundeText(nr) {
  const x = tele.runden[nr];
  return `${T("Runde", "Lap")} ${nr} · ${zeit(x.zeit_ms)}${nr === tele.beste ? T(" · Bestrunde", " · best lap") : ""}${!x.gueltig ? T(" · ungültig", " · invalid") : x.box ? T(" · Box", " · pit") : ""}`;
}

async function teleZeichnen() {
  const svg = $("tele-svg");
  if (!tele || !tele.runden) return;
  const nrA = Number($("tele-runde").value), nrB = Number($("tele-vergleich").value);
  const a = tele.runden[nrA], b0 = tele.runden[nrB];
  if (!a) return;
  const vergleich = teleModus === "vergleich";
  const b = vergleich && b0 && nrB !== nrA ? b0 : null;

  // Legende: Farben = Messgrößen, Linienart = Runde
  const chip = (farbe, text) => `<span><i style="background:${farbe}"></i>${text}</span>`;
  let leg = chip(TELE.tempo, T("Tempo", "Speed")) + chip(TELE.gas, T("Gas", "Throttle")) + chip(TELE.bremse, T("Bremse", "Brake"));
  if (vergleich) {
    leg += `<span class="trenner"></span><span><i style="background:#E6E8EC"></i>${esc(teleRundeText(nrA))}</span>`;
    if (b) leg += `<span><i class="gestrichelt" style="--f:#E6E8EC"></i>${esc(teleRundeText(nrB))}</span>`;
  }
  leg += `<span class="leise">${T("Maus über die Grafik für genaue Werte", "Hover over the chart for exact values")}</span>`;
  $("tele-legende").innerHTML = leg;

  const baender = vergleich
    ? [
        { id: "tempo", titel: T("Tempo", "Speed"), einheit: "km/h", o: 10, u: 170 },
        { id: "pedal", titel: T("Gas und", "Throttle"), titel2: T("Bremse", "& brake"), einheit: "%", o: 186, u: 296 },
        { id: "delta", titel: T("Zeit", "Time"), einheit: T("± s", "± s"), o: 312, u: 420 },
      ]
    : [
        { id: "tempo", titel: T("Tempo", "Speed"), einheit: "km/h", o: 10, u: 230 },
        { id: "pedal", titel: T("Gas und", "Throttle"), titel2: T("Bremse", "& brake"), einheit: "%", o: 248, u: 400 },
      ];
  const band = Object.fromEntries(baender.map((x) => [x.id, x]));
  const unten = baender[baender.length - 1].u;
  const hoehe = unten + 26;
  svg.style.height = hoehe + "px";
  const breite = svg.getBoundingClientRect().width || 1000;
  const links = 92, rechts = 14;
  const n = a.tempo.length;
  const x = (i) => links + (i / (n - 1)) * (breite - links - rechts);
  const vmax = Math.ceil((Math.max(...a.tempo, ...(b ? b.tempo : [0])) * 1.05) / 50) * 50 || 300;
  const yT = (v) => band.tempo.u - (v / vmax) * (band.tempo.u - band.tempo.o);
  const yP = (v) => band.pedal.u - v * (band.pedal.u - band.pedal.o - 6);
  const pfad = (werte, y) => werte.map((w, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(w).toFixed(1)}`).join("");
  const flaeche = (werte, y, boden) => `${pfad(werte, y)}L${x(n - 1).toFixed(1)},${boden}L${x(0).toFixed(1)},${boden}Z`;
  let s = "";

  // Bänder mit Titel links
  for (const bd of baender) {
    s += `<rect x="${links}" y="${bd.o}" width="${breite - links - rechts}" height="${bd.u - bd.o}" rx="6" fill="rgba(255,255,255,0.025)"></rect>`;
    s += `<text x="${links - 12}" y="${bd.o + 14}" text-anchor="end" font-size="12" font-weight="600" fill="#D5D8DE">${bd.titel}</text>`;
    let zy = bd.o + 29;
    if (bd.titel2) { s += `<text x="${links - 12}" y="${bd.o + 28}" text-anchor="end" font-size="12" font-weight="600" fill="#D5D8DE">${bd.titel2}</text>`; zy += 14; }
    s += `<text x="${links - 12}" y="${zy}" text-anchor="end" font-size="10.5" fill="${TELE.text}">${bd.einheit}</text>`;
  }
  for (let v = 50; v < vmax; v += 50) {
    if (v % 100 && vmax > 200 && !( !vergleich && vmax <= 300)) continue;
    s += `<line x1="${links}" x2="${breite - rechts}" y1="${yT(v)}" y2="${yT(v)}" stroke="${TELE.raster}"></line><text x="${links + 6}" y="${yT(v) - 4}" font-size="10" fill="${TELE.text}">${v}</text>`;
  }
  for (const v of [0.5]) s += `<line x1="${links}" x2="${breite - rechts}" y1="${yP(v)}" y2="${yP(v)}" stroke="${TELE.raster}"></line>`;

  // Kurven: beim Vergleich Bereich mit Zeitverlust rot hinterlegt
  let kurven = [];
  if (b) kurven = (await api().kurven(a, b, tele.laenge)) || [];
  for (const k of kurven) {
    const schlimm = k.verlust >= 0.1;
    if (schlimm && k.start != null && k.ende != null) {
      s += `<rect x="${x(k.start)}" y="${band.tempo.o}" width="${Math.max(2, x(k.ende) - x(k.start))}" height="${unten - band.tempo.o}" fill="rgba(255,122,110,0.07)"></rect>`;
    }
    s += `<line x1="${x(k.scheitel)}" x2="${x(k.scheitel)}" y1="${band.tempo.o}" y2="${unten}" stroke="${schlimm ? "rgba(255,122,110,0.45)" : "rgba(255,255,255,0.10)"}" stroke-dasharray="3 4"></line>`;
    s += `<text x="${x(k.scheitel)}" y="${band.tempo.o + 13}" text-anchor="middle" font-size="11" font-weight="700" fill="${schlimm ? TELE.schlecht : TELE.text}">${T("K", "T")}${k.kurve}</text>`;
  }

  // Tempo (gelb)
  if (!b) s += `<path d="${flaeche(a.tempo, yT, band.tempo.u)}" fill="rgba(255,200,61,0.08)"></path>`;
  if (b) s += `<path d="${pfad(b.tempo, yT)}" fill="none" stroke="${TELE.tempo}" stroke-opacity="0.75" stroke-width="1.6" stroke-dasharray="6 4"></path>`;
  s += `<path d="${pfad(a.tempo, yT)}" fill="none" stroke="${TELE.tempo}" stroke-width="2.2"></path>`;
  // Gas (grün) und Bremse (rot) übereinander in einem Feld, wie man es kennt
  s += `<path d="${flaeche(a.gas, yP, band.pedal.u)}" fill="rgba(61,220,132,0.16)"></path>`;
  s += `<path d="${flaeche(a.bremse, yP, band.pedal.u)}" fill="rgba(255,90,78,0.22)"></path>`;
  if (b) {
    s += `<path d="${pfad(b.gas, yP)}" fill="none" stroke="${TELE.gas}" stroke-opacity="0.75" stroke-width="1.5" stroke-dasharray="5 4"></path>`;
    s += `<path d="${pfad(b.bremse, yP)}" fill="none" stroke="${TELE.bremse}" stroke-opacity="0.8" stroke-width="1.5" stroke-dasharray="5 4"></path>`;
  }
  s += `<path d="${pfad(a.gas, yP)}" fill="none" stroke="${TELE.gas}" stroke-width="1.8"></path>`;
  s += `<path d="${pfad(a.bremse, yP)}" fill="none" stroke="${TELE.bremse}" stroke-width="1.8"></path>`;

  // Zeitunterschied (nur beim Vergleich): über der Mitte = langsamer (rot), darunter = schneller (grün)
  let delta = null;
  if (vergleich) {
    const dm = (band.delta.o + band.delta.u) / 2;
    if (b) {
      delta = a.zeit.map((z, i) => z - b.zeit[i]);
      const dmax = Math.max(0.3, ...delta.map(Math.abs)) * 1.1;
      const yD = (v) => dm - (v / dmax) * ((band.delta.u - band.delta.o) / 2 - 6);
      s += `<defs><clipPath id="d-oben"><rect x="0" y="${band.delta.o}" width="${breite}" height="${dm - band.delta.o}"></rect></clipPath>
        <clipPath id="d-unten"><rect x="0" y="${dm}" width="${breite}" height="${band.delta.u - dm}"></rect></clipPath></defs>`;
      s += `<line x1="${links}" x2="${breite - rechts}" y1="${dm}" y2="${dm}" stroke="rgba(255,255,255,0.18)"></line>`;
      s += `<path d="${flaeche(delta, yD, dm)}" fill="rgba(255,122,110,0.22)" clip-path="url(#d-oben)"></path>`;
      s += `<path d="${flaeche(delta, yD, dm)}" fill="rgba(61,220,132,0.22)" clip-path="url(#d-unten)"></path>`;
      s += `<path d="${pfad(delta, yD)}" fill="none" stroke="#F2F3F5" stroke-width="1.6"></path>`;
      s += `<text x="${links + 6}" y="${band.delta.o + 13}" font-size="10.5" fill="${TELE.schlecht}">${T("▲ langsamer als Vergleich", "▲ slower than comparison")}</text>`;
      s += `<text x="${links + 6}" y="${band.delta.u - 6}" font-size="10.5" fill="${TELE.gut}">${T("▼ schneller", "▼ faster")}</text>`;
      const ende = delta[delta.length - 1];
      s += `<text x="${links - 12}" y="${band.delta.o + 52}" text-anchor="end" font-size="15" font-weight="700" fill="${ende > 0 ? TELE.schlecht : TELE.gut}">${ende > 0 ? "+" : ""}${komma(ende, 2)}</text>`;
      s += `<text x="${links - 12}" y="${band.delta.o + 66}" text-anchor="end" font-size="10" fill="${TELE.text}">${T("im Ziel", "at the line")}</text>`;
    } else {
      s += `<text x="${links + 12}" y="${dm + 4}" font-size="12" fill="${TELE.text}">${T("Wähle bei „gegen“ eine andere Runde zum Vergleichen", "Pick a different lap under “vs” to compare")}</text>`;
    }
  }
// Strecke unten in Metern
  const laenge = tele.laenge || 0;
  if (laenge > 0) {
    for (let m = 0; m <= laenge; m += laenge > 4000 ? 1000 : 500) {
      const i = (m / laenge) * (n - 1);
      s += `<text x="${x(i)}" y="${unten + 18}" text-anchor="${m === 0 ? "start" : m + (laenge > 4000 ? 1000 : 500) > laenge ? "end" : "middle"}" font-size="10" fill="${TELE.text}">${m === 0 ? "0 m" : komma(m / 1000, 1) + " km"}</text>`;
    }
  }
  // Mauszeiger-Linie (wird beim Bewegen gesetzt)
  s += `<line id="tele-zeiger" x1="0" x2="0" y1="${band.tempo.o}" y2="${unten}" stroke="rgba(255,255,255,0.55)" stroke-width="1" visibility="hidden"></line>`;
  svg.setAttribute("viewBox", `0 0 ${breite} ${hoehe}`);
  svg.innerHTML = s;
  teleAktuell = { a, b, delta, n, links, rechts, breite, nrA, nrB, laenge, vergleich };

  // Schriftliche Auswertung: im Vergleich die gewählte Vergleichsrunde, sonst automatisch die Bestrunde
  let refNr = b ? nrB : null, refKurven = kurven;
  if (!b && tele.beste != null && tele.beste !== nrA && tele.runden[tele.beste]) {
    refNr = tele.beste;
    refKurven = (await api().kurven(a, tele.runden[refNr], tele.laenge)) || [];
  }
  teleAuswertung(nrA, refNr, refKurven, x, band.tempo.o, unten);
}

// --- Schriftliche Rundenauswertung -------------------------------------------
function kurvenTipp(k) {
  if (k.bremsen_m != null && k.bremsen_m <= -8)
    return [T(`Du bremst etwa ${-k.bremsen_m} Meter früher.`, `You brake about ${-k.bremsen_m} metres earlier.`),
            T("Setz den Bremspunkt Runde für Runde etwa 5 Meter später, bis du am Scheitel das Tempo der Vergleichsrunde hast.",
              "Move your braking point about 5 metres later each lap until you carry the apex speed of the reference lap."), "frueh"];
  if (k.tempo_diff <= -3)
    return [T(`Im Scheitel bist du ${Math.round(-k.tempo_diff)} km/h langsamer.`, `You are ${Math.round(-k.tempo_diff)} km/h slower at the apex.`),
            T("Weniger hart bremsen und mehr Schwung in die Kurve mitnehmen. Lass die Bremse sanfter los, damit das Auto besser einlenkt.",
              "Brake less hard and carry more speed into the corner. Release the brake more gently so the car turns in better."), "scheitel"];
  if (k.gas_m != null && k.gas_m >= 8)
    return [T(`Du gehst etwa ${k.gas_m} Meter später aufs Gas.`, `You get on the throttle about ${k.gas_m} metres later.`),
            T("Früher ans Gas: erst dosiert, dann voll, sobald du das Lenkrad öffnest.",
              "Get on the throttle earlier: gently first, then fully as soon as you unwind the wheel."), "gas"];
  if (k.bremsen_m != null && k.bremsen_m >= 8 && k.tempo_diff <= 0)
    return [T("Du bremst zu spät und kommst schlecht um die Kurve.", "You brake too late and don't get round the corner well."),
            T("Lieber ein paar Meter früher bremsen, damit das Auto am Scheitel ruhig ist und du früh ans Gas kommst.",
              "Brake a few metres earlier so the car is settled at the apex and you can get on the throttle early."), "spaet"];
  return [T("Kein einzelner Grund, eher Kleinigkeiten in der ganzen Kurve.", "No single reason, rather small things through the whole corner."),
          T("Achte auf eine saubere, gleiche Linie: gleicher Einlenkpunkt, gleicher Scheitel, Runde für Runde.",
            "Focus on a clean, repeatable line: same turn-in point, same apex, lap after lap."), "linie"];
}

function teleAuswertung(nrA, refNr, kurven, x, oben, unten) {
  const box = $("tele-auswertung"), liste = $("tele-kurven");
  const a = tele.runden[nrA];
  const hinweisUngueltig = !a.gueltig ? `<p class="warnung">${T("Diese Runde war ungültig (Track Limits). Sie zählt nicht als Bestzeit.", "This lap was invalid (track limits). It does not count as a best lap.")}</p>` : "";
  if (refNr == null) {
    box.innerHTML = `<h3>${T("Auswertung", "Analysis")}</h3>${hinweisUngueltig}<p>${nrA === tele.beste
      ? T("Das ist deine Bestrunde in dieser Session. Wähle oben „Runden vergleichen“, um sie mit einer anderen Runde zu vergleichen.", "This is your best lap of the session. Choose “Compare laps” above to compare it with another lap.")
      : T("Für eine Auswertung braucht es eine gültige Vergleichsrunde. Fahr noch eine saubere Runde.", "An analysis needs a valid reference lap. Drive another clean lap.")}</p>`;
    liste.innerHTML = "";
    return;
  }
  const ref = tele.runden[refNr];
  const diff = (a.zeit_ms && ref.zeit_ms) ? (a.zeit_ms - ref.zeit_ms) / 1000 : null;
  const refName = refNr === tele.beste ? T(`deine Bestrunde (Runde ${refNr})`, `your best lap (lap ${refNr})`) : T(`Runde ${refNr}`, `lap ${refNr}`);
  const verluste = kurven.filter((k) => k.verlust > 0.05).sort((p, q) => q.verlust - p.verlust);
  const gewinne = kurven.filter((k) => k.verlust < -0.05).sort((p, q) => p.verlust - q.verlust);
  const saetze = [];
  if (diff != null) {
    if (Math.abs(diff) < 0.05) saetze.push(T(`Runde ${nrA} ist praktisch genauso schnell wie ${refName}.`, `Lap ${nrA} is practically as fast as ${refName}.`));
    else if (diff > 0) saetze.push(T(`Runde ${nrA} ist <b>${komma(diff, 2)} s langsamer</b> als ${refName}.`, `Lap ${nrA} is <b>${komma(diff, 2)} s slower</b> than ${refName}.`));
    else saetze.push(T(`Runde ${nrA} ist <b class="gut">${komma(-diff, 2)} s schneller</b> als ${refName}.`, `Lap ${nrA} is <b class="gut">${komma(-diff, 2)} s faster</b> than ${refName}.`));
  }
  if (verluste.length && diff > 0.1) {
    const k = verluste[0], anteil = Math.min(100, Math.round((k.verlust / diff) * 100));
    saetze.push(anteil >= 40
      ? T(`Allein Kurve ${k.kurve} macht etwa ${anteil} % davon aus. Da liegt der größte Hebel.`, `Turn ${k.kurve} alone accounts for about ${anteil}% of that. That's your biggest lever.`)
      : T(`Die Zeit verteilt sich auf mehrere Kurven, am meisten in Kurve ${k.kurve}.`, `The time is spread over several corners, most of it in turn ${k.kurve}.`));
  } else if (!verluste.length) {
    saetze.push(T("In keiner Kurve geht wirklich Zeit verloren. Stark!", "No real time lost in any corner. Great!"));
  }
  if (gewinne.length) {
    const g = gewinne.slice(0, 2).map((k) => T(`Kurve ${k.kurve} (${komma(-k.verlust, 2)} s)`, `turn ${k.kurve} (${komma(-k.verlust, 2)} s)`));
    saetze.push(T(`Gut gemacht: Schneller warst du in ${g.join(" und ")}. Das kannst du so beibehalten.`, `Well done: you were quicker in ${g.join(" and ")}. Keep that.`));
  }
  box.innerHTML = `<h3>${T("Auswertung", "Analysis")}</h3>${hinweisUngueltig}<p>${saetze.join(" ")}</p>`;
  const schonGesagt = {};
  liste.innerHTML = verluste.slice(0, 3).map((k, i) => {
    let [grund, tipp, art] = kurvenTipp(k);
    if (schonGesagt[art]) tipp = T(`Gleiches Muster wie in Kurve ${schonGesagt[art]}, hier hilft derselbe Tipp.`, `Same pattern as in turn ${schonGesagt[art]}, the same tip helps here.`);
    else schonGesagt[art] = k.kurve;
    return `<div class="kurve-karte" data-s="${k.start}" data-e="${k.ende}"><div class="kopfzeile"><span class="k">${i + 1}. ${T("Kurve", "Turn")} ${k.kurve}</span><span class="v">+${komma(k.verlust, 2)} s</span></div>
      <div class="g">${esc(grund)}</div><div class="tipp">${esc(tipp)}</div></div>`;
  }).join("");
  // Maus über eine Karte: die Kurve in der Grafik hervorheben
  const svg = $("tele-svg");
  liste.querySelectorAll(".kurve-karte").forEach((karte) => {
    karte.onmouseenter = () => {
      let r = svg.querySelector("#tele-hervor");
      if (!r) { r = document.createElementNS("http://www.w3.org/2000/svg", "rect"); r.id = "tele-hervor"; svg.insertBefore(r, svg.firstChild); }
      const x1 = x(Number(karte.dataset.s)), x2 = x(Number(karte.dataset.e));
      r.setAttribute("x", x1); r.setAttribute("width", Math.max(2, x2 - x1)); r.setAttribute("y", oben); r.setAttribute("height", unten - oben);
      r.setAttribute("fill", "rgba(255,200,61,0.12)"); r.setAttribute("visibility", "visible");
    };
    karte.onmouseleave = () => { const r = svg.querySelector("#tele-hervor"); if (r) r.setAttribute("visibility", "hidden"); };
  });
}

// Maus über der Telemetrie: Werte an dieser Stelle anzeigen
function teleMaus(ev) {
  const t = teleAktuell, box = $("tele-tipp"), zeiger = $("tele-zeiger");
  if (!t || !zeiger) return;
  const svg = $("tele-svg"), r = svg.getBoundingClientRect();
  const px = (ev.clientX - r.left) * (t.breite / r.width);
  if (px < t.links || px > t.breite - t.rechts) { teleMausWeg(); return; }
  const i = Math.round(((px - t.links) / (t.breite - t.links - t.rechts)) * (t.n - 1));
  zeiger.setAttribute("x1", px); zeiger.setAttribute("x2", px); zeiger.setAttribute("visibility", "visible");
  const zeile = (name, farbe, wa, wb, einheit) => `<tr><td style="color:${farbe}">${name}</td><td>${wa}${einheit}</td>${t.b ? `<td class="b">${wb}${einheit}</td>` : ""}</tr>`;
  const pr = (v) => Math.round(v * 100);
  let html = `<div class="ort">${t.laenge ? Math.round((i / (t.n - 1)) * t.laenge) + " m" : Math.round((i / (t.n - 1)) * 100) + " %"}</div><table>`;
  if (t.b) html += `<tr><th></th><th>${T("R", "L")}${t.nrA}</th><th class="b">${T("R", "L")}${t.nrB} ┄</th></tr>`;
  html += zeile(T("Tempo", "Speed"), TELE.tempo, Math.round(t.a.tempo[i]), t.b ? Math.round(t.b.tempo[i]) : "", " km/h");
  html += zeile(T("Gas", "Throttle"), TELE.gas, pr(t.a.gas[i]), t.b ? pr(t.b.gas[i]) : "", " %");
  html += zeile(T("Bremse", "Brake"), TELE.bremse, pr(t.a.bremse[i]), t.b ? pr(t.b.bremse[i]) : "", " %");
  html += `</table>`;
  if (t.delta) {
    const d = t.delta[i];
    html += `<div class="d" style="color:${d > 0 ? TELE.schlecht : TELE.gut}">${d > 0 ? "+" : ""}${komma(d, 2)} s ${d > 0 ? T("langsamer", "slower") : T("schneller", "faster")}</div>`;
  }
  box.innerHTML = html;
  box.hidden = false;
  const wrap = box.parentElement.getBoundingClientRect();
  let left = ev.clientX - wrap.left + 16;
  if (left + box.offsetWidth > wrap.width - 8) left = ev.clientX - wrap.left - box.offsetWidth - 16;
  box.style.left = `${left}px`;
  box.style.top = `${Math.max(8, ev.clientY - wrap.top - box.offsetHeight / 2)}px`;
}
function teleMausWeg() {
  const box = $("tele-tipp"), zeiger = $("tele-zeiger");
  if (box) box.hidden = true;
  if (zeiger) zeiger.setAttribute("visibility", "hidden");
}
$("tele-svg").addEventListener("mousemove", teleMaus);
$("tele-svg").addEventListener("mouseleave", teleMausWeg);

window.addEventListener("resize", () => {
  if (seite === "auswertung") $("session-auswahl").dispatchEvent(new Event("change"));
});

// ---------------------------------------------------------------- Ansagen und Einstellungen
function stimmenFuellen(stimmen) {
  D.stimmen = stimmen;
  const liste = stimmen.map(([id, name, da]) => [id, da ? name : name + T("  (noch laden)", "  (download first)")]);
  const aktuell = stimmen.some((s) => s[0] === E.stimme) ? E.stimme : (stimmen[0] || [""])[0];
  optionen($("stimme"), liste, aktuell);
}
function gewaehlteStimme() { return D.stimmen.find((s) => s[0] === $("stimme").value); }
function stimmStatus(text, art = "") { const s = $("stimme-status"); s.textContent = text; s.className = "status-text " + art; }

function themenAufbauen() {
  const box = $("thema-wahl");
  box.innerHTML = "";
  for (const [id, t] of Object.entries(THEMEN)) {
    const b = document.createElement("button");
    b.type = "button";
    b.innerHTML = `<i style="background:linear-gradient(135deg, ${t.l[0][0]} 0 50%, ${t.l[1][0]} 50% 100%)${id === "nacht" ? ";background:#15161a" : ""}"></i>${esc(T(t.de, t.en))}`;
    b.classList.toggle("an", (E.thema || THEMA_STANDARD) === id);
    b.setAttribute("aria-pressed", String((E.thema || THEMA_STANDARD) === id));
    b.onclick = () => { themaSetzen(id); speichern({ thema: id }); themenAufbauen(); };
    box.appendChild(b);
  }
}

function einstellungenAufbauen() {
  themenAufbauen();
  // Ansagen
  segment($("gespraechig"), D.gespraechig, D.gespraechig[E.gespraechig ?? 1], (w) => speichern({ gespraechig: D.gespraechig.indexOf(w) }));
  $("ansagen-schalter").innerHTML = D.ansagen.map(([s, t]) =>
    `<label class="schalter"><input type="checkbox" data-ansage="${esc(s)}"${E.ansagen[s] ? " checked" : ""}><span class="bahn"></span><span>${esc(t)}</span></label>`).join("");
  $("ansagen-schalter").querySelectorAll("input").forEach((i) => (i.onchange = () => {
    E.ansagen[i.dataset.ansage] = i.checked; speichern({ ansagen: E.ansagen });
  }));
  // Stimme
  stimmenFuellen(D.stimmen);
  // Neural-Stimmen: erst nach einem Hinweis (inoffizieller Microsoft-Dienst)
  let stimmeVorher = E.stimme;
  $("neural-text").textContent = D.neural_hinweis || "";
  const neuralFrage = (an) => { $("neural-hinweis").hidden = !an; };
  $("neural-ok").onclick = () => {
    E.neural_ok = true; neuralFrage(false);
    speichern({ neural_ok: true });
    $("stimme").dispatchEvent(new Event("change"));
  };
  $("neural-nein").onclick = () => { neuralFrage(false); $("stimme").value = stimmeVorher; };
  $("stimme").onchange = () => {
    const s = gewaehlteStimme();
    if (s && s[0].startsWith("edge:") && !E.neural_ok) { neuralFrage(true); return; }
    neuralFrage(false);
    if (s && !s[2]) stimmStatus(T('Diese Stimme muss erst geladen werden. Klick auf „Laden“.', 'This voice has to be downloaded first. Click “Download”.'));
    else { stimmStatus(""); speichern({ stimme: s[0] }); stimmeVorher = s[0]; }
  };
  $("stimme-laden").onclick = () => {
    const s = gewaehlteStimme();
    if (s && s[0].startsWith("edge:") && !E.neural_ok) { neuralFrage(true); return; }
    if (!s || s[0].startsWith("windows:")) return stimmStatus(T("Windows-Stimmen sind schon da, nichts zu laden.", "Nothing to download."));
    if (s[2]) return stimmStatus(T("Diese Stimme ist schon geladen.", "This voice is already downloaded."));
    $("stimme-laden").disabled = true; stimmStatus(T("Starte Download ...", "Starting download ...")); api().stimme_laden(s[0]);
  };
  $("stimme-testen").onclick = () => {
    const s = gewaehlteStimme();
    if (s && s[0].startsWith("edge:") && !E.neural_ok) { neuralFrage(true); return; }
    if (s && !s[2]) return stimmStatus(T("Erst auf „Laden“ klicken, dann anhören.", "Click “Download” first, then listen."));
    if (s) E.stimme = s[0];
    api().speichern({ stimme: E.stimme }).then(() => api().stimme_testen());
    stimmStatus(T("Spiele Probe ab ...", "Playing sample ...")); setTimeout(() => stimmStatus(""), 3000);
  };
  $("aussprache").onclick = () => api().aussprache_oeffnen();
  segment($("funk-effekt"), D.funk_stufen, D.funk_stufen[E.funk], (w) => speichern({ funk: D.funk_stufen.indexOf(w) }));
  for (const name of ["tempo", "lautstaerke"]) {
    const r = $(name), w = $(name + "-wert");
    r.value = E[name]; w.textContent = E[name];
    r.oninput = () => { w.textContent = r.value; speichern({ [name]: Number(r.value) }, false); };
  }
  const namen = [...D.ingenieur_namen];
  if (E.ingenieur_name && !namen.includes(E.ingenieur_name)) namen.push(E.ingenieur_name);
  segment($("ingenieur-name"), namen, E.ingenieur_name || namen[0], (w) => speichern({ ingenieur_name: w }));
  const ansprache = { auto: T("Auto und Platz", "Car and position"), name: T("Mit Namen", "By name") };
  segment($("gegner-ansprache"), Object.keys(ansprache), E.gegner_ansprache || "auto", (w) => speichern({ gegner_ansprache: w }), (w) => ansprache[w]);
  $("fahrer-name").value = E.fahrer_name || "";
  $("fahrer-name").oninput = () => speichern({ fahrer_name: $("fahrer-name").value.trim() }, false);
  $("begruessung").checked = !!E.begruessung;
  $("begruessung").onchange = () => speichern({ begruessung: $("begruessung").checked });
  // Steuerung
  $("funktaste").textContent = D.funktaste;
  $("funktaste-lernen").onclick = async () => {
    const r = await api().funktaste_lernen();
    if (r && r.fehler) return toast(r.fehler, true);
    $("funktaste-lernen").disabled = true; $("start-knopf").disabled = true;
    $("funktaste").textContent = T("Jetzt die Taste drücken (15 Sekunden) ...", "Press the button now (15 seconds) ..."); $("funktaste").className = "gelb";
  };
  optionen($("mikrofon"), [["", T("Windows-Standard", "Windows default")], ...D.mikrofone.map((m) => [m, m])], E.mikrofon || "");
  $("mikrofon").onchange = () => speichern({ mikrofon: $("mikrofon").value });
  optionen($("modell"), D.modelle.map(([n, t]) => [n, `${t} (${n})`]), E.modell);
  $("modell").onchange = () => speichern({ modell: $("modell").value });
  // KI
  $("ki-an").checked = !!E.ki;
  $("ki-an").onchange = () => speichern({ ki: $("ki-an").checked });
  optionen($("ki-modell"), D.ki_modelle, E.ki_modell);
  $("ki-modell").onchange = () => { speichern({ ki_modell: $("ki-modell").value }); kiStatus(T("Prüfe ...", "Checking ..."), ""); api().speichern({ ki_modell: $("ki-modell").value }).then(() => api().ki_pruefen()); };
  const geraete = { grafikkarte: T("Grafikkarte (schnell)", "Graphics card (fast)"), prozessor: T("Prozessor (keine FPS-Einbußen)", "Processor (no FPS loss)") };
  segment($("ki-geraet"), Object.keys(geraete), E.ki_geraet || "grafikkarte", (w) => speichern({ ki_geraet: w }), (w) => geraete[w]);
  $("ki-laden").onclick = () => { $("ki-laden").disabled = true; kiStatus(T("Starte Download ...", "Starting download ..."), "gelb"); api().ki_laden(); };
  $("ollama").onclick = () => api().webseite("https://ollama.com/download");
  $("ki-pruefen").onclick = () => { kiStatus(T("Prüfe ...", "Checking ..."), ""); api().ki_pruefen(); };
  // KI online oder lokal
  const anbieter = { groq: T("Online: Groq (empfohlen)", "Online: Groq (recommended)"), gemini: "Online: Google Gemini", lokal: T("Auf diesem PC", "On this PC") };
  const seiten = { gemini: "https://aistudio.google.com/apikey", groq: "https://console.groq.com/keys" };
  const kiArtZeigen = () => {
    const a = E.ki_anbieter || "groq", online = a !== "lokal";
    document.querySelectorAll(".nur-online").forEach((el) => (el.style.display = online ? "" : "none"));
    document.querySelectorAll(".nur-lokal").forEach((el) => (el.style.display = online ? "none" : ""));
    if (online) $("ki-schluessel").value = E["schluessel_" + a] || "";
    $("erkennung-hinweis").textContent = E.erkennung_online && !E.schluessel_groq ? T("Groq-Schlüssel fehlt noch", "Groq key still missing") : "";
  };
  segment($("ki-anbieter"), Object.keys(anbieter), E.ki_anbieter || "groq", (w) => {
    E.ki_anbieter = w; kiArtZeigen(); kiStatus(T("Prüfe ...", "Checking ..."), "");
    api().speichern({ ki_anbieter: w }).then(() => api().ki_pruefen());
  }, (w) => anbieter[w]);
  $("ki-schluessel").onchange = () => {
    const a = E.ki_anbieter, wert = $("ki-schluessel").value.trim();
    E["schluessel_" + a] = wert; kiArtZeigen(); kiStatus(T("Prüfe ...", "Checking ..."), "");
    const teil = { ["schluessel_" + a]: wert };
    if (wert && !E.ki) { teil.ki = true; E.ki = true; $("ki-an").checked = true; }   // Schlüssel da: KI gleich an
    api().speichern(teil).then(() => api().ki_pruefen());
  };
  $("schluessel-holen").onclick = () => api().webseite(seiten[E.ki_anbieter] || seiten.groq);
  $("ki-online-pruefen").onclick = () => { kiStatus(T("Prüfe ...", "Checking ..."), ""); api().ki_pruefen(); };
  $("erkennung-online").checked = !!E.erkennung_online;
  $("erkennung-online").onchange = () => { E.erkennung_online = $("erkennung-online").checked; speichern({ erkennung_online: E.erkennung_online }); kiArtZeigen(); };
  kiArtZeigen();
  // Sprache (gilt nach einem Neustart des Programms)
  segment($("sprache"), D.sprachen.map(([k]) => k), E.sprache || "de", (w) => {
    E.sprache = w;
    api().speichern({ sprache: w });
    $("sprache-neustart").style.display = w !== D.sprache ? "" : "none";
  }, (w) => Object.fromEntries(D.sprachen)[w]);
  $("sprache-neustart").style.display = "none";
  $("sprache-neustart").onclick = () => api().neustart();
  // Strategie und Programm
  const reserveText = (r) => String(r).replace(".", T(",", "."));
  const reserve = D.reserven.reduce((a, r) => (Math.abs(r - E.reserve_runden) < Math.abs(a - E.reserve_runden) ? r : a), D.reserven[0]);
  segment($("reserve"), D.reserven, reserve, (w) => speichern({ reserve_runden: w }), reserveText);
  // Zusatz-Anzeigen
  $("overlay").checked = !!E.overlay;
  $("overlay").onchange = async () => { E.overlay = $("overlay").checked; await api().overlay(E.overlay); };
  $("handy").checked = !!E.handy;
  const handyZeigen = (r) => { $("handy-adresse").textContent = r && r.an ? `${T("Am Handy öffnen", "Open on your phone")}: ${r.adresse}` : ""; if (r && r.fehler) toast(T("Handy-Anzeige: ", "Phone view: ") + r.fehler, true); };
  $("handy").onchange = async () => { E.handy = $("handy").checked; handyZeigen(await api().handy(E.handy)); };
  if (E.handy) setTimeout(async () => handyZeigen(await api().handy(true)), 1500);
  $("version-text").textContent = `${D.produkt || ""} ${D.version || ""}`.trim();
  $("lizenzen").onclick = () => api().lizenzen_oeffnen();
  $("fehler-melden").onclick = async () => {
    const r = await api().fehler_melden();
    if (r && r.datei) toast(T("Fehlerbericht erstellt. Bitte an die E-Mail anhängen.", "Bug report created. Please attach it to the email."));
    else if (r && r.fehler) toast(r.fehler, true);
  };
  // Projekt unterstützen: Knöpfe nur zeigen, wenn ein Link eingetragen ist
  $("newsletter-knopf").hidden = !D.newsletter;
  $("spenden-knopf").hidden = !D.spenden;
  $("unterstuetzen-zeile").hidden = !D.newsletter && !D.spenden;
  $("newsletter-knopf").onclick = () => api().webseite(D.newsletter);
  $("spenden-knopf").onclick = () => api().webseite(D.spenden);
  $("webseite-knopf").onclick = () => api().webseite("https://pitvoice.com");
  $("unterstuetzen-nav").hidden = !D.newsletter && !D.spenden;
  $("unterstuetzen-nav").onclick = () => { zeigen("einstellungen"); setTimeout(() => $("unterstuetzen-zeile").scrollIntoView({ behavior: "smooth", block: "center" }), 50); };
  $("verknuepfung").onclick = async () => {
    const r = await api().verknuepfung();
    if (r && r.fehler) toast(T("Verknüpfung hat nicht geklappt: ", "Shortcut didn't work: ") + r.fehler, true);
    else toast(T("„PitVoice AI“ liegt jetzt auf dem Desktop.", "“PitVoice AI” is now on the desktop."));
  };
  // Befehle
  $("befehle").innerHTML = D.befehle.map(([titel, saetze]) =>
    `<div class="tafel glas"><h2>${esc(titel)}</h2>${saetze.map((s) => `<div class="satz">${T("„", "“")}${esc(s)}${T("“", "”")}</div>`).join("")}</div>`).join("");
}
function kiStatus(text, art) { const s = $("ki-status"); s.textContent = text; s.className = "status-text " + art; }

// ---------------------------------------------------------------- Nachrichten vom Python-Teil
function verarbeiten(n) {
  const [art, a, b] = n;
  switch (art) {
    case "status": zustandSetzen(a, b); break;
    case "log": funkEintrag(a, b); if (a === "fehler") toast(b, true); break;
    case "info": if (zustand === "bereit") cockpitZeigen(a); break;
    case "feld":
      feld = a;
      if (fokus !== null && !feld.autos.some((x) => x.index === fokus)) fokus = null;
      if (seite === "live") liveZeigen();
      break;
    case "protokoll":
      aktuelleSession = a;
      if ($("session-auswahl").value === "aktuell" || !$("session-auswahl").value) auswertungZeigen(a);
      break;
    case "funk": { const f = $("funk-anzeige"); f.textContent = a ? T("Du funkst ...", "You're on the radio ...") : ""; f.className = "funk-anzeige funkt"; break; }
    case "denkt": { const f = $("funk-anzeige"); f.textContent = a ? `${ingName()} ${T("überlegt ...", "is thinking ...")}` : ""; f.className = "funk-anzeige denkt"; break; }
    case "fehler": funkEintrag("fehler", a); toast(a, true); break;
    case "download": stimmStatus(a); break;
    case "download_fertig":
      $("stimme-laden").disabled = false;
      if (b) { stimmStatus(""); toast(T("Stimme laden hat nicht geklappt: ", "Downloading the voice didn't work: ") + b, true); }
      else api().stimmen().then((liste) => { E.stimme = a; stimmenFuellen(liste); speichern({ stimme: a }); stimmStatus(T("Fertig! Klick auf „Anhören“.", "Done! Click “Listen”."), "gruen"); });
      break;
    case "ki_status": kiStatus(a, { rot: "rot", gelb: "", gruen: "gruen" }[b] ?? ""); break;
    case "ki_fertig":
      $("ki-laden").disabled = false;
      if (a) { kiStatus(T("Laden fehlgeschlagen", "Download failed"), "rot"); toast(T("KI-Modell: ", "AI model: ") + a, true); }
      else { $("ki-an").checked = true; E.ki = true; kiStatus(T("Bereit", "Ready"), "gruen"); }
      break;
    case "update":
      $("update-titel").textContent = T(`Neue Version ${a.version} verfügbar`, `New version ${a.version} available`);
      $("update-text").textContent = a.neu || T("Lade sie auf der Download-Seite herunter.", "Get it from the download page.");
      $("update-laden").hidden = !a.seite;
      $("update-laden").onclick = () => { api().webseite(a.seite); $("update-band").hidden = true; };
      $("update-zu").onclick = () => { $("update-band").hidden = true; };
      $("update-band").hidden = false;
      break;
    case "lernen_fertig":
      $("funktaste-lernen").disabled = false;
      if (zustand === "aus") $("start-knopf").disabled = false;
      if (b) { toast(b, true); $("funktaste").className = ""; }
      else { $("funktaste").textContent = a; $("funktaste").className = "gruen"; }
      break;
  }
}

let holtGerade = false;
async function abholen() {
  if (holtGerade) return;
  holtGerade = true;
  try {
    const liste = await api().abholen();
    if (Array.isArray(liste)) liste.forEach(verarbeiten);
  } catch (fehler) { console.error(fehler); }
  holtGerade = false;
}


// ---------------------------------------------------------------- Kästen mit der Maus größer/kleiner ziehen
// Cockpit: Trenner zwischen Pitboard und Funk, und über der Strategie-Leiste.
// Live-Karte: Trenner zwischen Karte und Rangliste, und zwischen Karte und Fahrer-Tabelle.
// Doppelklick auf einen Trenner stellt die normale Größe wieder her. Wird in den Einstellungen gemerkt.
const AUF_STANDARD = { cockpit_spalte: 0.608, cockpit_unten: 150, live_spalte: 0.608, live_zeile: 0.583 };
const AUF_GRENZEN = { cockpit_spalte: [0.3, 0.8], cockpit_unten: [90, 420], live_spalte: [0.3, 0.8], live_zeile: [0.2, 0.88] };
let auf = { ...AUF_STANDARD };
const TEILER = [];

function aufteilungAnwenden() {
  const st = document.documentElement.style;
  st.setProperty("--cockpit-spalten", `minmax(0, ${auf.cockpit_spalte}fr) minmax(0, ${1 - auf.cockpit_spalte}fr)`);
  st.setProperty("--cockpit-unten", `${auf.cockpit_unten}px`);
  st.setProperty("--live-spalten", `minmax(0, ${auf.live_spalte}fr) minmax(0, ${1 - auf.live_spalte}fr)`);
  st.setProperty("--live-zeilen", `minmax(0, ${auf.live_zeile}fr) minmax(0, ${1 - auf.live_zeile}fr)`);
  requestAnimationFrame(teilerPlatzieren);
}

function teilerPlatzieren() {
  for (const t of TEILER) {
    const vor = t.vor();
    if (!vor || !vor.offsetWidth) continue;
    if (t.art === "spalte") {
      t.el.style.left = `${vor.offsetLeft + vor.offsetWidth}px`;
      t.el.style.top = `${vor.offsetTop}px`;
      t.el.style.height = `${t.hoehe ? t.hoehe() : vor.offsetHeight}px`;
    } else if (t.art === "zeile") {
      t.el.style.top = `${vor.offsetTop + vor.offsetHeight}px`;
      t.el.style.left = `${vor.offsetLeft}px`;
      t.el.style.width = `${vor.offsetWidth}px`;
    }
  }
}

function teilerAnlegen(behaelter, art, schluessel, vor, berechnen, hoehe) {
  const el = document.createElement("div");
  el.className = `teiler ${art}`;
  el.title = T("Ziehen zum Anpassen · Doppelklick = normale Größe", "Drag to resize · double-click = default size");
  behaelter.appendChild(el);
  const t = { el, art, vor, hoehe };
  TEILER.push(t);
  el.addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    el.setPointerCapture(ev.pointerId);
    el.classList.add("zieht");
    document.body.classList.add(art === "spalte" ? "zieht-spalte" : "zieht-zeile");
  });
  el.addEventListener("pointermove", (ev) => {
    if (!el.hasPointerCapture(ev.pointerId)) return;
    const [min, max] = AUF_GRENZEN[schluessel];
    auf[schluessel] = Math.min(max, Math.max(min, berechnen(ev, behaelter.getBoundingClientRect())));
    aufteilungAnwenden();
  });
  const los = (ev) => {
    if (!el.classList.contains("zieht")) return;
    el.classList.remove("zieht");
    document.body.classList.remove("zieht-spalte", "zieht-zeile");
    speichern({ aufteilung: { ...auf } });
  };
  el.addEventListener("pointerup", los);
  el.addEventListener("pointercancel", los);
  el.addEventListener("dblclick", () => { auf[schluessel] = AUF_STANDARD[schluessel]; aufteilungAnwenden(); speichern({ aufteilung: { ...auf } }); });
  new ResizeObserver(teilerPlatzieren).observe(behaelter);
}

function teilerAufbauen() {
  auf = { ...AUF_STANDARD, ...(E.aufteilung || {}) };
  const cockpit = document.querySelector(".cockpit-raster");
  const cSeite = document.querySelector('.seite[data-seite="cockpit"]');
  const live = document.querySelector(".live-raster");
  teilerAnlegen(cockpit, "spalte", "cockpit_spalte", () => cockpit.querySelector(".pitboard"),
    (ev, r) => (ev.clientX - r.left) / r.width);
  teilerAnlegen(cSeite, "zeile", "cockpit_unten", () => cockpit,
    (ev, r) => r.bottom - ev.clientY - 8);
  teilerAnlegen(live, "spalte", "live_spalte", () => live.querySelector(".karte"),
    (ev, r) => (ev.clientX - r.left) / r.width,
    () => live.offsetHeight);
  teilerAnlegen(live, "zeile", "live_zeile", () => live.querySelector(".karte"),
    (ev, r) => (ev.clientY - r.top) / r.height);
  window.addEventListener("resize", teilerPlatzieren);
  aufteilungAnwenden();
}

// ---------------------------------------------------------------- Start
async function starten() {
  D = await api().anfang();
  if (!D || D.fehler) { toast("Start fehlgeschlagen / start failed: " + (D && D.fehler), true); return; }
  E = D.e;
  SPRACHE = D.sprache || "de";
  themaSetzen(E.thema);
  seiteUebersetzen();
  E.ansagen = E.ansagen || {};
  einstellungenAufbauen();
  teilerAufbauen();
  zustandSetzen(D.zustand);
  funkEintrag("system", T("Drück auf Starten. Dann Funktaste halten und sprechen.", "Press Start. Then hold the radio button and speak."));
  sessionsAktualisieren();
  auswertungZeigen(null);
  setInterval(abholen, 150);
}
if (window.pywebview && window.pywebview.api && window.pywebview.api.anfang) starten();
else window.addEventListener("pywebviewready", starten);
