// Pure helpers for the Assignments list rows.

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** "Period 2 Reading · Grade 3 · 24 students", omitting any part the data does not have. */
export function assignmentMeta(assignment, classes) {
  if (!assignment) return "";
  const cls = Array.isArray(classes) ? classes.find((c) => c.id === assignment.classId) : undefined;
  const name = assignment.className || cls?.name || "";
  const grade = cls && cls.grade != null && cls.grade !== "" ? `Grade ${cls.grade}` : "";
  const students = cls && Number.isFinite(cls.students) ? plural(cls.students, "student") : "";
  return [name, grade, students].filter(Boolean).join(" · ");
}

export const soundAlongLabel = (on) => (on ? "Sound Along on" : "Sound Along off");
