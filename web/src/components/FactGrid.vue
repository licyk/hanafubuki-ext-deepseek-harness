<script lang="ts">
/** One labelled fact: what it is, and what it reads. */
export interface Fact {
  label: string;
  value: string;
  /** Monospace, for a version, a commit or a path. */
  mono?: boolean;
}
</script>

<script setup lang="ts">
// The three-column labelled grid the application's version panel heads its
// sections with: a caption-strong label above a body value, `auto` columns
// that collapse to as many as the width allows.
defineProps<{ facts: Fact[] }>();
</script>

<template>
  <dl class="facts">
    <div v-for="fact in facts" :key="fact.label" class="facts__item">
      <dt class="facts__label">{{ fact.label }}</dt>
      <dd class="facts__value" :class="{ 'facts__value--mono': fact.mono }">{{ fact.value }}</dd>
    </div>
  </dl>
</template>

<style scoped>
.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--space-3) var(--space-5);
  margin: 0;
}

.facts__item {
  min-width: 0;
}

.facts__label {
  color: var(--text-secondary);
  font: var(--type-caption-strong);
}

/* The pair rather than `--type-body`, which would also reset the mono family. */
.facts__value {
  margin-top: var(--space-1);
  font-size: var(--font-size-body);
  line-height: var(--line-height-body);
  overflow-wrap: anywhere;
  user-select: text;
}

.facts__value--mono {
  font-family: var(--font-mono);
}
</style>
