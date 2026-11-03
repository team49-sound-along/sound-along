<script setup>
import { setRole } from "../session.js";
</script>

<template>
  <div class="page">
    <section class="card only" aria-labelledby="to-h">
      <h2 id="to-h">Teacher only</h2>
      <p class="muted">This page is for teachers. Students can read passages from the Library and My assignments.</p>
      <div class="row">
        <a class="btn primary" href="#/library">Go to the Library</a>
        <button class="btn" type="button" @click="setRole('teacher')">Switch to Teacher view</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.only { display: grid; gap: var(--s2); justify-items: start; max-width: 560px; }
.row { display: flex; gap: var(--s1); flex-wrap: wrap; }
</style>
