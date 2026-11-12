<script setup lang="ts">
// The kit's info bar (`info-bar`, class API 1) with the glyph it leaves to
// the page: information, a warning or an error.
defineProps<{ severity?: "warning" | "error"; message: string }>();
</script>

<template>
  <div class="info-bar" :data-severity="severity" :role="severity === 'error' ? 'alert' : 'status'">
    <svg class="info-bar__icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
      <template v-if="severity === 'warning'">
        <path d="M10 3 2.5 16.5h15z" stroke-linejoin="round" />
        <path d="M10 8v4M10 14.2v.1" stroke-linecap="round" />
      </template>
      <template v-else-if="severity === 'error'">
        <circle cx="10" cy="10" r="7.5" />
        <path d="m7.5 7.5 5 5m0-5-5 5" stroke-linecap="round" />
      </template>
      <template v-else>
        <circle cx="10" cy="10" r="7.5" />
        <path d="M10 9v4.5M10 6.3v.1" stroke-linecap="round" />
      </template>
    </svg>
    <p class="info-bar__text">
      <span class="info-bar__message">{{ message }}</span>
    </p>
  </div>
</template>
