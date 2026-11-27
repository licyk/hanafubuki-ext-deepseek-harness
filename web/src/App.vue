<script setup lang="ts">
// One management section of the instance: dsh's versions, the Node.js it
// runs, or its configuration. It is the page's whole frame — the host lists
// the three in the instance's rail and opens one at a time — so this file is
// what each of them wears: the section's one refresh at the header's
// trailing end, and an info bar for what an action reported. Everything else
// comes from the backend through the frame client (`status`, `versions`,
// `checkUpdate`, `copyHome`); no page has a network of its own.
import { computed, onMounted, ref, watch } from "vue";
import * as client from "hanafubuki-frame";
import { InfoBar, RefreshButton } from "hanafubuki-ui";

import { useVersionPage } from "./composables/useVersionPage";

const page = useVersionPage();

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
      <span class="page__spacer" aria-hidden="true" />
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

    <slot />
  </main>
</template>

<style scoped>
/* One column of sections, 12 apart (the application's section spacing), with
   the section's one refresh at the trailing end of the header. */
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

/* The refresh sits at the trailing end, the place the application's panel
   header puts a section's actions (spec §7.21). The section's own name is the
   host's — the rail entry and the panel header — so the page does not repeat
   it; the spacer keeps the button where that header would. */
.page__spacer {
  flex: 1 1 auto;
  min-width: 0;
}
</style>
