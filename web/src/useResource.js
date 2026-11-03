import { onBeforeUnmount, ref } from "vue";

/** Loads async data with loading/error state. `load()` runs immediately and on reload(). */
export function useResource(load) {
  const data = ref(null);
  const loading = ref(true);
  const error = ref("");
  let alive = true;
  let seq = 0;

  async function reload() {
    const mine = ++seq;
    loading.value = true;
    error.value = "";
    try {
      const result = await load();
      if (alive && mine === seq) data.value = result;
    } catch (e) {
      if (alive && mine === seq) error.value = e?.message || "Something went wrong. Please try again.";
    } finally {
      if (alive && mine === seq) loading.value = false;
    }
  }
  onBeforeUnmount(() => (alive = false));
  reload();
  return { data, loading, error, reload };
}
