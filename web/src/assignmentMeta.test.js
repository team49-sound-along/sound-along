import { test } from "node:test";
import assert from "node:assert/strict";
import { assignmentMeta, soundAlongLabel } from "./assignmentMeta.js";

const classes = [{ id: "c1", name: "Period 2 Reading", grade: 3, students: 24 }];

test("full line from assignment and class data", () => {
  assert.equal(assignmentMeta({ className: "Period 2 Reading", classId: "c1" }, classes), "Period 2 Reading · Grade 3 · 24 students");
});
test("omits missing parts", () => {
  assert.equal(assignmentMeta({ className: "X", classId: "zz" }, classes), "X");
  assert.equal(assignmentMeta({ classId: "c1" }, classes), "Period 2 Reading · Grade 3 · 24 students");
  assert.equal(assignmentMeta({ className: "X" }, undefined), "X");
  assert.equal(assignmentMeta({}, classes), "");
  assert.equal(assignmentMeta(null, classes), "");
});
test("singular student and zero-safe", () => {
  assert.equal(assignmentMeta({ classId: "a" }, [{ id: "a", name: "N", grade: 1, students: 1 }]), "N · Grade 1 · 1 student");
  assert.equal(assignmentMeta({ classId: "a" }, [{ id: "a", name: "N", students: 0 }]), "N · 0 students");
});
test("does not mutate inputs", () => {
  const a = Object.freeze({ className: "X", classId: "c1" });
  assert.doesNotThrow(() => assignmentMeta(a, Object.freeze([...classes])));
});
test("soundAlongLabel", () => {
  assert.equal(soundAlongLabel(true), "Sound Along on");
  assert.equal(soundAlongLabel(false), "Sound Along off");
});

import { gradeLabel } from "./assignmentMeta.js";
test("a grade is never shown as 'Grade Grade 3'", () => {
  assert.equal(gradeLabel("Grade 3"), "Grade 3");
  assert.equal(gradeLabel(3), "Grade 3");
  assert.equal(gradeLabel(""), "");
  assert.equal(assignmentMeta({ classId: "c" }, [{ id: "c", name: "P", grade: "Grade 3", students: 24 }]), "P · Grade 3 · 24 students");
});
