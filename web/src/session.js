// Synthetic signed-in user and role. No real auth: role is a demo switch persisted per browser.
import { ref, readonly } from "vue";

export const USERS = {
  teacher: { role: "teacher", label: "Ms. Rivera", initials: "MR" },
  student: { role: "student", label: "Jordan, Grade 4", initials: "J4" },
};
const KEY = "soundalong.role";

function load() {
  try {
    const v = localStorage.getItem(KEY);
    return v === "student" ? "student" : "teacher";
  } catch {
    return "teacher";
  }
}

const roleRef = ref(load());
export const role = readonly(roleRef);

export function setRole(next) {
  if (!USERS[next]) return;
  roleRef.value = next;
  try {
    localStorage.setItem(KEY, next);
  } catch {
    /* storage unavailable: role still works for this page view */
  }
}
