// Which language a pasted text is written in, so Spanish text is never read by the English voice (or the other way round).
// Counts very common words of each language in the first 400 words and answers only when the evidence is clear. Words that exist in both languages are left out.
const EN = new Set("the and of to in is was that it with for as she they her his their you are were be this on at by from had have not but what all we can there when which who will would one said been has into than then them these those your our how out up about".split(" "));
const ES = new Set("el la los las de que y en un una es se por con para su sus al lo como más pero sin sobre entre cuando muy también ya fue está hay del le les nos mi yo él ella ellos ellas eso esto esta este estos estas era eran tiene tienen había qué cómo dónde porque aunque hasta desde donde cada todo todos toda todas otro otra".split(" "));
const MIN_HITS = 8;
const RATIO = 3;

/** "en", "es", or null when the text is too short or too mixed to tell. */
export function guessLanguage(text) {
  const words = String(text ?? "").toLowerCase().match(/[a-záéíóúüñ]+/g)?.slice(0, 400) ?? [];
  let en = 0;
  let es = 0;
  for (const w of words) {
    if (EN.has(w)) en += 1;
    if (ES.has(w)) es += 1;
  }
  if (es >= MIN_HITS && es >= RATIO * (en + 1)) return "es";
  if (en >= MIN_HITS && en >= RATIO * (es + 1)) return "en";
  return null;
}
