<script setup lang="ts">
// The band under a section's facts: the verdict of the update check, when it
// answered, the control that runs it again, and the components the verdict is
// made of. It is the application's own update band (`VersionsPanel`) with one
// addition — a manual check — because this page's check is the only thing
// that re-reads the registry on demand.
import { computed } from "vue";
import { StatusBadge, UpdateHint } from "hanafubuki-ui";

import { localDateTime } from "../lib/format";
import type { UpdateCheck } from "../types";

const props = defineProps<{
  check: UpdateCheck | null;
  checking: boolean;
  disabled?: boolean;
  /** The line the check's verdict reads as. */
  verdict: string;
  /** Whether the band offers its own manual check. */
  checkable?: boolean;
  /** What the check just ran for, said over the band while it is in flight. */
  checkLabel: string;
  /** The manual check's label, and its label while it runs. */
  checkAction: string;
  checkingLabel: string;
  /** Shown where no check has answered yet. */
  unknownLabel: string;
  /** The Node.js component's row, when the instance downloads its own. */
  nodeLabel: string;
  /** The update available hint's label. */
  updateLabel: string;
}>();

const emit = defineEmits<{ check: [] }>();
const latest = computed(() => props.check?.components?.find((part) => part.name === "node") ?? null);
</script>

<template>
  <div class="band">
    <div class="band__verdict">
      <StatusBadge
        v-if="check"
        :tone="check.hasUpdate ? 'warning' : 'success'"
        :dot="checking"
        :pulse="checking"
      >
        {{ verdict }}
      </StatusBadge>
      <span v-else class="band__note">{{ unknownLabel }}</span>
      <span v-if="check" class="band__time">
        {{ checkLabel.replace("{time}", localDateTime(check.checkedAt)) }}
      </span>
    </div>
    <div v-if="checkable" class="band__actions">
      <UpdateHint
        v-if="check?.hasUpdate"
        :text="verdict"
        :label="updateLabel"
      />
      <button
        type="button"
        class="btn btn-sm"
        :disabled="checking || disabled"
        @click="emit('check')"
      >
        {{ checking ? checkingLabel : checkAction }}
      </button>
    </div>
    <dl v-if="latest" class="band__parts">
      <dt>{{ nodeLabel }}</dt>
      <dd>
        <span class="band__mono">{{
          [latest.current, latest.latest !== latest.current ? latest.latest : null]
            .filter(Boolean)
            .join(" → ") || "—"
        }}</span>
      </dd>
    </dl>
  </div>
</template>

<style scoped>
.band {
  display: grid;
  gap: var(--space-2);
}

.band__verdict {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.band__note,
.band__time {
  color: var(--text-secondary);
  font: var(--type-caption);
}

.band__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.band__parts {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: var(--space-1) var(--space-3);
  margin: 0;
  color: var(--text-secondary);
  font: var(--type-caption);
}

.band__parts dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.band__mono {
  font-family: var(--font-mono);
}
</style>
