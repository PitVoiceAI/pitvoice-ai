// Farbthemen: die Lichter hinter dem Glas. Wird von der App, dem Overlay und der Handy-Ansicht benutzt.
// Jedes Licht: [Farbe, Deckkraft]
const THEMEN = {
  kupfer:   { de: "Orange & Kupfer",  en: "Orange & copper",  l: [["#FF8A1F", 0.24], ["#B5562A", 0.26], ["#7A3414", 0.16]] },
  gold:     { de: "Gold & Nachtblau", en: "Gold & midnight",  l: [["#FFB020", 0.22], ["#1F4BFF", 0.24], ["#0B2A8F", 0.14]] },
  petrol:   { de: "Petrol & Blau",    en: "Petrol & blue",    l: [["#12B5A6", 0.22], ["#2456FF", 0.24], ["#0E6F8F", 0.14]] },
  eis:      { de: "Eisblau & Gold",   en: "Ice blue & gold",  l: [["#3FA9F5", 0.22], ["#FFB020", 0.22], ["#1B5FA8", 0.14]] },
  silber:   { de: "Silber & Blau",    en: "Silver & blue",    l: [["#9FB3C8", 0.16], ["#2F6BFF", 0.22], ["#5C6F86", 0.14]] },
  klassik:  { de: "Orange & Lila",    en: "Orange & purple",  l: [["#FF8A1F", 0.26], ["#6D5BFF", 0.22], ["#1E7BFF", 0.15]] },
  strecke:  { de: "Grün & Rot",       en: "Green & red",      l: [["#19C26C", 0.22], ["#E5332A", 0.22], ["#0F8F4F", 0.12]] },
  nacht:    { de: "Ganz dunkel",      en: "All dark",         l: [["#FFFFFF", 0.0], ["#FFFFFF", 0.0], ["#FFFFFF", 0.0]] },
};
const THEMA_STANDARD = "kupfer";

function themaSetzen(id) {
  const t = THEMEN[id] || THEMEN[THEMA_STANDARD];
  const st = document.documentElement.style;
  t.l.forEach(([farbe, deckkraft], i) => {
    st.setProperty(`--licht-${i + 1}`, farbe);
    st.setProperty(`--licht-${i + 1}-d`, deckkraft);
  });
  document.documentElement.dataset.thema = THEMEN[id] ? id : THEMA_STANDARD;
}
