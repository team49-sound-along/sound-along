// What the reader does when the word being spoken moves.
// Normally the page scrolls (smoothly) to keep that word in view. With "Reduce motion" the page never moves by itself:
// when the word is off screen the reader offers a button, and the person decides when to jump.

/** @returns {"none" | "scroll" | "offer-jump"} `rect` is the word's bounding box, `bottomLimit` the lowest visible line (above the player). */
export function followAction({ reduce, rect, topLimit = 190, bottomLimit }) {
  const visible = rect.top >= topLimit && rect.bottom <= bottomLimit;
  if (visible) return "none";
  return reduce ? "offer-jump" : "scroll";
}
