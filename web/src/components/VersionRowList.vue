<script setup lang="ts">
// The version list, as the application's version management draws it: ruled
// rows inside one bordered box, the identifier with its pills, and the row's
// own action at the trailing end. Everything visual comes from the UI kit
// (`btn`, `btn-sm`) and the components (`StatusBadge`, `EmptyState`,
// `LoadMoreSentinel`); this file owns only the metric the kit has no class
// for — the bordered list and its 48px rows.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import type { ComponentPublicInstance } from "vue";
import { EmptyState, LoadMoreSentinel, StatusBadge } from "hanafubuki-ui";

import { VERSION_BATCH } from "../lib/format";

/**
 * One version row. The application's own version list maps its records onto
 * this shape, and so does this page: the list itself carries no registry or
 * package vocabulary.
 */
export interface VersionRow {
  /** Rendered identifier, stable row key, and the value handed back on activate. */
  id: string;
  /** Marked with an "Installed" pill instead of carrying a switch button. */
  isCurrent: boolean;
  /** Already-translated status pills, drawn after the identifier. */
  badges?: string[];
  /** Already-translated `title` for this row's switch button. */
  switchTitle: string;
  /** Secondary text at the trailing end, before the action: a publication date, a resolved version. */
  detail?: string;
}

const props = withDefaults(
  defineProps<{
    rows: VersionRow[];
    /** What every row's list is about, so a new subject starts the reveal again. */
    sourceKey: string;
    busy?: boolean;
    switchable?: boolean;
    /** Shown centred in the box when there are no rows. */
    emptyText?: string;
    /** Fill the remaining height of a flex-column parent and scroll inside it. */
    fill?: boolean;
    /** The row's switch button, in the page's language. */
    switchLabel: string;
    /** The pill a current row carries, in the page's language. */
    installedLabel: string;
    /** What the row that asks for the next batch says. */
    loadingLabel: string;
  }>(),
  { busy: false, switchable: true, emptyText: undefined, fill: false },
);

const emit = defineEmits<{ activate: [id: string] }>();

const shown = ref(VERSION_BATCH);
watch(
  () => [props.sourceKey, props.rows] as const,
  () => (shown.value = VERSION_BATCH),
);

const visible = computed(() => props.rows.slice(0, shown.value));
const hasMore = computed(() => props.rows.length > visible.value.length);
const showEmpty = computed(() => Boolean(props.emptyText) && props.rows.length === 0);

// `LoadMoreSentinel` is a presentation row and observes nothing; the list
// asks for the next batch as its last row nears the viewport, so a registry
// with hundreds of versions paints a page of them, not all of them.
const sentinel = ref<ComponentPublicInstance | null>(null);
let observer: IntersectionObserver | null = null;
watch(sentinel, (component) => {
  observer?.disconnect();
  if (component) observer?.observe(component.$el as HTMLElement);
});
onBeforeUnmount(() => observer?.disconnect());

if (typeof IntersectionObserver !== "undefined") {
  observer = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting) && hasMore.value) shown.value += VERSION_BATCH;
  });
}

function activate(row: VersionRow): void {
  if (!row.isCurrent && !props.busy) emit("activate", row.id);
}
</script>

<template>
  <ul class="rows" :class="{ 'rows--fill': fill, 'rows--empty': showEmpty }">
    <!-- The border is on the list, so an empty state sits inside it: drawing
         it in the caller made the box disappear. -->
    <li v-if="showEmpty" class="rows__empty">
      <EmptyState :text="emptyText!" />
    </li>
    <li
      v-for="row in visible"
      :key="row.id"
      class="rows__row"
      :aria-current="row.isCurrent ? 'true' : undefined"
    >
      <div class="rows__info">
        <code class="rows__id" :title="row.id">{{ row.id }}</code>
        <span v-if="row.badges?.length" class="rows__badges">
          <StatusBadge v-for="badge in row.badges" :key="badge">{{ badge }}</StatusBadge>
        </span>
      </div>
      <div class="rows__action">
        <span v-if="row.detail" class="rows__detail">{{ row.detail }}</span>
        <StatusBadge v-if="row.isCurrent" tone="accent">
          {{ installedLabel }}
        </StatusBadge>
        <!-- One per row, so not the view's primary action. -->
        <button
          v-else-if="switchable"
          type="button"
          class="btn btn-sm rows__switch"
          :disabled="busy"
          :title="row.switchTitle"
          @click="activate(row)"
        >
          {{ switchLabel }}
        </button>
      </div>
    </li>
    <LoadMoreSentinel
      v-if="hasMore"
      ref="sentinel"
      class="rows__sentinel"
      :label="loadingLabel"
    />
  </ul>
</template>

<style scoped>
.rows {
  display: grid;
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
  border: 1px solid var(--stroke-card);
  border-radius: var(--radius-control);
  grid-auto-rows: max-content;
  align-content: start;
}

/* The list is the panel's remaining height, and only it scrolls. */
.rows--fill {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
}

/* An empty message centres in the whole box, not in a content-sized row. */
.rows--empty {
  grid-auto-rows: minmax(0, 1fr);
  align-content: stretch;
  min-height: 160px;
}

.rows__empty {
  display: flex;
  min-height: 0;
}

.rows__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-3);
  min-height: 48px;
  padding: var(--space-1) var(--space-2);
}

.rows__row + .rows__row {
  border-top: 1px solid var(--stroke-divider);
}

.rows__info {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-1) var(--space-2);
  min-width: 0;
  padding: var(--space-0-5) var(--space-1);
}

.rows__id {
  min-width: 0;
  font-family: var(--font-mono);
  font-size: var(--font-size-body);
  line-height: var(--line-height-body);
  overflow-wrap: anywhere;
  user-select: text;
}

.rows__badges {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.rows__action {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-2);
}

.rows__detail {
  color: var(--text-secondary);
  font: var(--type-caption);
  white-space: nowrap;
}

.rows__switch {
  white-space: nowrap;
}

/* Ruled like the rows above it. */
.rows__sentinel {
  border-top: 1px solid var(--stroke-divider);
}
</style>
