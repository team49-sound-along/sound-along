// Pure helpers for the Assignments list rows.

/** "Grade 3" whether the data says 3 or "Grade 3". */
export const gradeLabel = (grade) => (grade == null || grade === "" ? "" : /^grade\b/i.test(String(grade).trim()) ? String(grade).trim() : `Grade ${grade}`);

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** "Period 2 Reading · Grade 3 · 24 students", omitting any part the data does not have. */
export function assignmentMeta(assignment, classes) {
  if (!assignment) return "";
  const cls = Array.isArray(classes) ? classes.find((c) => c.id === assignment.classId) : undefined;
  const name = assignment.className || cls?.name || "";
  const grade = cls ? gradeLabel(cls.grade) : "";
  const students = cls && Number.isFinite(cls.students) ? plural(cls.students, "student") : "";
  return [name, grade, students].filter(Boolean).join(" · ");
}

export const soundAlongLabel = (on) => (on ? "Sound Along on" : "Sound Along off");
