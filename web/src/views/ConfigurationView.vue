<script setup lang="ts">
// Configuration: where dsh keeps its homes, which of them this instance uses,
// and the copy of the user's own into it. The registry and the Node.js mirror
// are the extension's Settings fields, named here so a reader looking for them
// knows where they are; this page changes none of them.
import { computed } from "vue";
import { InfoBar, ProgressBar } from "hanafubuki-ui";

import FactGrid from "../components/FactGrid.vue";
import SectionShell from "../components/SectionShell.vue";
import { useVersionPage } from "../composables/useVersionPage";

const page = useVersionPage();

const status = computed(() => page.status.value);

const facts = computed(() => {
  const found = status.value;
  return [
    {
      label: page.t("home"),
      value: found?.homePath ?? page.t("homeUser"),
      mono: Boolean(found?.homePath),
    },
    {
      label: page.t("paths"),
      value: found?.nodePath ?? "—",
      mono: true,
    },
    {
      label: page.t("registry"),
      value: page.versions.value?.registry ?? "—",
      mono: true,
    },
  ];
});

const blocked = computed(() => page.busy.value || status.value?.running === true);
</script>

<template>
  <SectionShell :title="page.t('home')">
    <FactGrid :facts="facts" />

    <p v-if="status?.homePath" class="note">{{ page.t("homeHint") }}</p>
    <p class="note">{{ page.t("settingsHint") }}</p>

    <div v-if="status?.canCopyHome" class="actions">
      <button type="button" class="btn" :disabled="blocked || status.copying" @click="page.copyHome()">
        {{ page.t("copyHome") }}
      </button>
    </div>
    <ProgressBar v-if="status?.copying" :value="null" :label="page.t('copyHome')" />
    <InfoBar
      :open="Boolean(status?.canCopyHome)"
      severity="info"
      :message="page.t('copyHomeHint')"
    />
  </SectionShell>
</template>

<style scoped>
.note {
  margin: 0;
  color: var(--text-secondary);
  font: var(--type-caption);
  overflow-wrap: anywhere;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
</style>
