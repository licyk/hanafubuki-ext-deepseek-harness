<script setup lang="ts">
// Node.js: which one the instance runs, which version its install values ask
// for, and whether an update would move it. This page reports; it does not
// choose. `nodeVersion` is one of the type's install parameters, so the
// maintenance panel's install form owns changing it, and a switch of dsh from
// the versions page keeps whatever that form recorded.
import { computed } from "vue";
import { InfoBar, StatusBadge } from "hanafubuki-ui";

import FactGrid from "../components/FactGrid.vue";
import SectionShell from "../components/SectionShell.vue";
import { useVersionPage } from "../composables/useVersionPage";

const page = useVersionPage();

const status = computed(() => page.status.value);

/** The Node.js component of the update check, when the instance downloads its own. */
const component = computed(
  () => page.check.value?.components?.find((part) => part.name === "node") ?? null,
);

const facts = computed(() => {
  const found = status.value;
  return [
    {
      label: page.t("node"),
      value: found
        ? found.nodeSource === "own"
          ? page.t("nodeOwn", { version: found.node ?? page.t("unknown") })
          : (found.node ?? page.t("unknown"))
        : page.t("loading"),
      mono: true,
    },
    {
      label: page.t("requestedNode"),
      value: found?.nodeVersion ?? page.t("nodeFromInstall"),
      mono: true,
    },
    {
      label: page.t("paths"),
      value: found?.nodeSource === "prefix" ? (found.prefix ?? "—") : (found?.nodePath ?? "—"),
      mono: true,
    },
  ];
});

/** How this instance gets its Node.js, as one sentence. */
const source = computed(() => {
  const found = status.value;
  if (!found) return "";
  if (found.nodeSource === "prefix") return page.t("nodePrefix", { prefix: found.prefix ?? "" });
  if (found.nodeSource === "own") return page.t("nodeExternal", { path: found.nodePath });
  return page.t("nodeManaged", { version: found.nodeVersion ?? "—" });
});
</script>

<template>
  <SectionShell :title="page.t('node')">
    <FactGrid :facts="facts" />

    <div v-if="component" class="verdict">
      <StatusBadge :tone="component.hasUpdate ? 'warning' : 'success'">
        {{
          component.hasUpdate
            ? page.t("updateAvailable")
            : page.t("upToDate")
        }}
      </StatusBadge>
      <span class="verdict__detail">
        <span class="verdict__mono">{{
          [component.current, component.latest !== component.current ? component.latest : null]
            .filter(Boolean)
            .join(" → ") || "—"
        }}</span>
      </span>
    </div>

    <InfoBar :open="Boolean(source)" severity="info" :message="source" />
    <p class="note">{{ page.t("nodeMaintenance") }}</p>
  </SectionShell>
</template>

<style scoped>
.verdict {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.verdict__detail {
  color: var(--text-secondary);
  font: var(--type-caption);
}

.verdict__mono {
  font-family: var(--font-mono);
}

.note {
  margin: 0;
  color: var(--text-secondary);
  font: var(--type-caption);
  overflow-wrap: anywhere;
}
</style>
