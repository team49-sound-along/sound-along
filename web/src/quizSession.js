// The quiz attempt in progress, kept in memory only. Opening "Show me where" leaves the quiz screen; coming back (Back button) resumes
// exactly where the student was. Closing the tab forgets it. Finished scores are saved separately by quiz.js.
import { reactive } from "vue";

const attempts = new Map();
let counter = 0;

const fresh = (docId) => reactive({ seed: `${docId}:${Date.now()}:${(counter += 1)}`, answers: {}, index: 0, finished: false });

/** The attempt for these questions, started when there is none. */
export function attemptFor(docId) {
  if (!attempts.has(docId)) attempts.set(docId, fresh(docId));
  return attempts.get(docId);
}

/** Retry: a new attempt, with the choices shuffled again. */
export function restartAttempt(docId) {
  attempts.set(docId, fresh(docId));
  return attempts.get(docId);
}
