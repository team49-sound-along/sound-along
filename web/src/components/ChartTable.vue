<script setup>
// The text alternative every chart carries: the same numbers as a table, opened with a plain disclosure button.
defineProps({ caption: { type: String, required: true }, columns: { type: Array, required: true }, rows: { type: Array, required: true } });
</script>

<template>
  <details class="ct">
    <summary>Show as a table</summary>
    <div class="table-wrap" tabindex="0" role="region" :aria-label="`${caption}, table`">
      <table class="data">
        <caption class="sr-only">{{ caption }}</caption>
        <thead><tr><th v-for="c in columns" :key="c" scope="col">{{ c }}</th></tr></thead>
        <tbody>
          <tr v-for="(row, n) in rows" :key="n"><td v-for="(cell, k) in row" :key="k">{{ cell }}</td></tr>
        </tbody>
      </table>
    </div>
  </details>
</template>

<style scoped>
.ct { font-size: 14px; }
.table-wrap { position: relative; }
.ct summary { cursor: pointer; min-height: 32px; display: flex; align-items: center; color: var(--muted); font-weight: 600; }
</style>
