/** Sliding-window limiter keyed by caller. Returns a function: allow(key) -> boolean. */
export function createRateLimiter({ max, windowMs, now = Date.now }) {
  const hits = new Map();
  return function allow(key) {
    const t = now();
    const recent = (hits.get(key) ?? []).filter((time) => t - time < windowMs);
    if (recent.length >= max) {
      hits.set(key, recent);
      return false;
    }
    hits.set(key, [...recent, t]);
    return true;
  };
}
