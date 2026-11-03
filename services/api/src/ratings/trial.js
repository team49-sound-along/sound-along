import { randomUUID } from "node:crypto";
import { HttpError } from "../http.js";
import { UUID } from "../recordings/rules.js";
import { TOKEN } from "./manifest.js";

export const TRIAL_PROMPT = "Which narration sounds more natural to read along with?";
const PREFERRED = new Set(["a", "b", "tie"]);

const bad = (message) => {
  throw new HttpError(400, message);
};
const pick = (items, random) => items[Math.min(items.length - 1, Math.floor(random() * items.length))];

/** A random AI-vs-other pair of one passage in random a/b order, or null when no passage has both. Never exposes kinds. */
export function buildTrial(clips, random = Math.random, newId = randomUUID) {
  const byPassage = new Map();
  for (const clip of clips) byPassage.set(clip.passageId, [...(byPassage.get(clip.passageId) ?? []), clip]);
  const eligible = [...byPassage.values()].filter((group) => group.some((c) => c.kind === "ai") && group.some((c) => c.kind !== "ai"));
  if (eligible.length === 0) return null;
  const group = pick(eligible, random);
  const ai = pick(group.filter((c) => c.kind === "ai"), random);
  const other = pick(group.filter((c) => c.kind !== "ai"), random);
  const [a, b] = random() < 0.5 ? [ai, other] : [other, ai];
  const view = (c) => ({ token: c.token, url: `/data/ab/${c.token}.mp3` });
  return { trialId: newId(), title: ai.title, prompt: TRIAL_PROMPT, a: view(a), b: view(b) };
}

const parseScore = (value, label) => {
  if (!Number.isInteger(value) || value < 1 || value > 5) bad(`${label} must be a whole number from 1 to 5.`);
  return value;
};

/** Validate a POST /api/ratings body against the manifest. Returns the rating to store (without createdAt). */
export function parseRating(body, clips) {
  if (body === null || typeof body !== "object" || Array.isArray(body)) bad("Send a JSON object.");
  if (typeof body.trialId !== "string" || !UUID.test(body.trialId)) bad("That listening round is not valid. Load a new one.");
  for (const field of ["aToken", "bToken"]) {
    if (typeof body[field] !== "string" || !TOKEN.test(body[field])) bad("Those clips are not valid. Load a new round.");
  }
  const clipA = clips.find((c) => c.token === body.aToken);
  const clipB = clips.find((c) => c.token === body.bToken);
  if (!clipA || !clipB) bad("We could not find those clips. Load a new round.");
  if (clipA.token === clipB.token || clipA.passageId !== clipB.passageId) bad("Those two clips are not from the same passage.");
  if ([clipA, clipB].filter((c) => c.kind === "ai").length !== 1) bad("One clip in each round must be the AI voice.");
  if (!PREFERRED.has(body.preferred)) bad('Choose "a", "b" or "tie".');
  const ratingA = parseScore(body.ratingA, "Rating for clip A");
  const ratingB = parseScore(body.ratingB, "Rating for clip B");
  if (body.raterId != null && !(typeof body.raterId === "string" && UUID.test(body.raterId))) bad("That listener id is not valid.");
  const other = clipA.kind === "ai" ? clipB : clipA;
  const winner = { a: clipA, b: clipB }[body.preferred];
  return {
    trialId: body.trialId,
    passageId: clipA.passageId,
    comparison: `ai vs ${other.kind}`,
    preferredKind: winner ? winner.kind : "tie",
    kindA: clipA.kind,
    kindB: clipB.kind,
    ratingA,
    ratingB,
    raterId: body.raterId ?? null,
  };
}
