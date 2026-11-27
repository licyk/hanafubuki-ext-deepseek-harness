<script setup lang="ts">
// A section of the page: its title, an optional hint beside it, the section's
// actions at the trailing end, and its content. The application's management
// panels are headed the same way, so a section here reads like one of theirs.
defineProps<{ title: string }>();
</script>

<template>
  <section class="section">
    <header class="section__head">
      <h2 class="section__title">{{ title }}</h2>
      <div v-if="$slots.hint" class="section__hint">
        <slot name="hint" />
      </div>
      <div class="section__actions">
        <slot name="actions" />
      </div>
    </header>
    <slot />
  </section>
</template>

<style scoped>
.section {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
  min-height: 0;
}

.section__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2) var(--space-3);
}

.section__title {
  margin: 0;
  font: var(--type-body-strong);
}

/* The hint takes the row's width: what it holds is a band, not a sentence. */
.section__hint {
  flex: 1 1 auto;
  min-width: 0;
}

.section__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  flex: 0 0 auto;
}

</style>
