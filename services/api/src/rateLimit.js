/**
 * Sliding-window limiter keyed by caller. Returns allow(key) -> boolean; allow.size() is the number of tracked keys.
 * Keys whose hits have all expired are dropped on every call, so the map cannot grow without bound.
 */
export function createRateLimiter({ max, windowMs, now = Date.now }) {
  const hits = new Map();

  function evictExpired(t) {
    for (const [key, times] of hits) {
      if (times.every((time) => t - time >= windowMs)) hits.delete(key);
    }
  }

  function allow(key) {
    const t = now();
    evictExpired(t);
    const recent = (hits.get(key) ?? []).filter((time) => t - time < windowMs);
    if (recent.length >= max) {
      hits.set(key, recent);
      return false;
    }
    hits.set(key, [...recent, t]);
    return true;
  }

  allow.size = () => hits.size;
  return allow;
}
