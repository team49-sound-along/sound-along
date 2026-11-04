import { fetchQuestions } from "./api.js";
import { chooseQuestions, questionSources } from "./quiz.js";

/**
 * The approved questions a passage can offer, or null. Looks in order: the passage's own file, its voice pair's, the other language's.
 * Stops at the first source that has any, so a passage with its own questions makes one request.
 */
export async function loadQuiz(id, timing, fetchDoc = fetchQuestions) {
  const sources = questionSources(id, timing);
  const docs = {};
  for (const source of sources) {
    docs[source.id] = await fetchDoc(source.id);
    const found = chooseQuestions([source], docs, id);
    if (found) return chooseQuestions(sources, docs, id);
  }
  return null;
}
