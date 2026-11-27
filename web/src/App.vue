<script setup lang="ts">
// The instance's frame: one page of three sections — dsh versions, Node.js,
// and the instance's configuration — chosen by the application's tab strip.
// Everything comes from the backend through the frame client (`status`,
// `versions`, `checkUpdate`, `copyHome`); the page has no network of its own.
//
// The shape follows the application's own instance management: a header with
// the section's one refresh at the trailing end, an info bar for what an
// action reported, and sections whose facts and lists use the UI kit's
// metrics. The views own their content; this file owns the page.
import { computed, onMounted, ref, watch } from "vue";
import * as client from "hanafubuki-frame";
import { BaseTabs, InfoBar, RefreshButton } from "hanafubuki-ui";

import ConfigurationView from "./views/ConfigurationView.vue";
import NodeView from "./views/NodeView.vue";
import VersionsView from "./views/VersionsView.vue";
import { useVersionPage } from "./composables/useVersionPage";

const page = useVersionPage();

const view = ref("versions");
const showPrereleases = ref(true);

const tabs = computed(() => [
  { value: "versions", label: page.t("versions") },
  { value: "node", label: page.t("nodeTab") },
  { value: "configuration", label: page.t("configurationTab") },
]);

/** The bar's text and severity, kept while it collapses so it leaves with what it showed. */
const bar = ref<{ text: string; severity: "info" | "error" }>({ text: "", severity: "info" });
const barOpen = computed(() => Boolean(page.message.value));

// A message is text and severity: the bar keeps both, so it collapses with
// what it showed rather than emptying itself first.
watch(
  () => page.message.value,
  (text) => {
    if (text) bar.value = { text, severity: page.failed.value ? "error" : "info" };
  },
);

onMounted(() => {
  client.ready();
  // The copy runs on in the backend; it says here when it is done, and the
  // page reads the instance again so the button it leaves behind is right.
  client.on("home-copied", (payload) => {
    const done = payload as { error?: string | null } | null;
    void page.load().then(() => {
      if (done?.error) page.report(done.error, true);
    });
  });
  void page.load();
});
</script>

<template>
  <main class="page">
    <header class="page__head">
      <div class="page__tabs">
        <BaseTabs v-model="view" :items="tabs" :label="page.t('tabs')" />
      </div>
      <RefreshButton
        :label="page.t('refresh')"
        :busy="page.refreshing.value"
        :disabled="page.loading.value || page.busy.value"
        @click="page.refresh()"
      />
    </header>

    <InfoBar
      :open="barOpen"
      :severity="bar.severity"
      :message="bar.text"
      @dismiss="page.message.value = ''"
    />

    <VersionsView v-if="view === 'versions'" v-model:show-prereleases="showPrereleases" />
    <NodeView v-else-if="view === 'node'" />
    <ConfigurationView v-else />
  </main>
</template>

<style scoped>
/* One column of groups, 12 apart (the application's section spacing), with the
   section's one refresh at the trailing end of the header. */
.page {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3);
  min-height: 0;
}

.page__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

/* The tabs take the row's width so the refresh sits at its trailing end, as
   the application's panel header puts its actions (spec §7.21). */
.page__tabs {
  flex: 1 1 auto;
  min-width: 0;
}
</style>
