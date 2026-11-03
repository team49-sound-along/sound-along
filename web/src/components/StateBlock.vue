<script setup>
// Shared loading / error / empty presentation.
defineProps({
  loading: Boolean,
  error: { type: String, default: "" },
  empty: Boolean,
  emptyTitle: { type: String, default: "Nothing here yet" },
  emptyText: { type: String, default: "" },
  loadingLabel: { type: String, default: "Loading" },
});
const emit = defineEmits(["retry"]);
</script>

<template>
  <div v-if="loading" class="state" role="status" aria-live="polite">
    <span class="spinner" aria-hidden="true"></span>
    <span>{{ loadingLabel }}&hellip;</span>
  </div>
  <div v-else-if="error" class="notice error" role="alert">
    <div class="msg">
      <strong>We could not load this.</strong>
      <p>{{ error }}</p>
    </div>
    <button class="btn" type="button" @click="emit('retry')">Try again</button>
  </div>
  <div v-else-if="empty" class="state empty">
    <strong>{{ emptyTitle }}</strong>
    <p v-if="emptyText" class="muted">{{ emptyText }}</p>
    <slot />
  </div>
  <slot v-else />
</template>

<style scoped>
.state { display: flex; align-items: center; gap: 12px; padding: var(--s3); color: var(--muted); }
.state.empty { flex-direction: column; align-items: flex-start; border: 1px dashed var(--border); border-radius: var(--r); background: var(--surface); }
.state.empty strong { color: var(--text); font-size: 18px; }
.notice.error { align-items: center; justify-content: space-between; flex-wrap: wrap; }
.msg { display: grid; gap: 2px; }
.spinner { width: 18px; height: 18px; border-radius: 50%; border: 3px solid var(--border); border-top-color: var(--primary); animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
