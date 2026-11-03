<script setup>
defineProps({ label: String, value: String, source: String, emphasis: Boolean });
</script>

<template>
  <div class="kpi card">
    <p class="eyebrow">{{ label }}</p>
    <p class="value num"><span :class="{ hl: emphasis }">{{ value }}</span></p>
    <p class="small muted">{{ source }}</p>
  </div>
</template>

<style scoped>
.kpi { display: grid; gap: 6px; padding: var(--s2) var(--s3); }
.value { font-size: 32px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.2; }
.hl { background: var(--hl); color: var(--on-hl); padding: 0 8px; border-radius: 6px; margin-left: -8px; }
</style>
