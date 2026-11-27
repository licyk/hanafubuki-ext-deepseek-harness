<script setup lang="ts">
// dsh versions: the facts of what is installed, the verdict of the update
// check, and every published version as its own switchable row. This is the
// application's version management (gestione/VersionsPanel + VersionEntryList)
// shaped onto a dsh that npm publishes: a package list has no branch, commit
// or date to head a section with, so its facts are the current and latest
// version and how many the registry lists.
import { computed } from "vue";
import { BaseSwitch, LoadingState } from "hanafubuki-ui";

import FactGrid from "../components/FactGrid.vue";
import SectionShell from "../components/SectionShell.vue";
import UpdateBand from "../components/UpdateBand.vue";
import VersionRowList from "../components/VersionRowList.vue";
import type { VersionRow } from "../components/VersionRowList.vue";
import { isPrerelease, publishedDate } from "../lib/format";
import { useVersionPage } from "../composables/useVersionPage";

const page = useVersionPage();

const showPrereleases = defineModel<boolean>("showPrereleases", { default: true });

/** The `latest` dist-tag, which the list marks as it does its own. */
const latestTag = computed(() => page.versions.value?.distTags?.latest ?? null);

/** The versions to show, newest first, pre-releases filtered as asked. */
const available = computed(() =>
  (page.versions.value?.versions ?? []).filter(
    (entry) => showPrereleases.value || !isPrerelease(entry.version),
  ),
);

/** The registry's rows: one per version, the installed one marked in place. */
const rows = computed<VersionRow[]>(() => {
  const installed = page.status.value?.installed ?? null;
  return available.value.map((entry) => {
    const badges: string[] = [];
    if (entry.version === latestTag.value) badges.push(page.t("latest"));
    if (isPrerelease(entry.version)) badges.push(page.t("prerelease"));
    return {
      id: entry.version,
      isCurrent: entry.version === installed,
      badges: badges.length ? badges : undefined,
      switchTitle: page.t("switchTo", { version: entry.version }),
      detail: publishedDate(entry.published),
    };
  });
});

/** The dist-tags, which a switch may name instead of a version. */
const tagRows = computed<VersionRow[]>(() => {
  const installed = page.status.value?.installed ?? null;
  const tags = page.versions.value?.distTags ?? {};
  return Object.entries(tags).map(([tag, version]) => ({
    id: tag,
    isCurrent: version === installed,
    badges: [version],
    switchTitle: page.t("switchTo", { version }),
  }));
});

const facts = computed(() => [
  {
    label: page.t("currentVersion"),
    value: page.status.value?.installed ?? page.t("notInstalled"),
    mono: true,
  },
  {
    label: page.t("latestVersion"),
    value: latestTag.value ?? "—",
    mono: true,
  },
  {
    label: page.t("availableVersions"),
    value: String(page.versions.value?.versions.length ?? 0),
  },
]);

const verdict = computed(() => {
  const found = page.check.value;
  if (!found) return "";
  if (!found.hasUpdate) return page.t("upToDate");
  const from = found.current ?? "—";
  const to = found.latest ?? "—";
  return `${page.t("updateAvailable")}: ${from} → ${to}`;
});

const checkLabel = computed(() => page.strings.value.checkedAt ?? "Checked {time}");

const running = computed(() => page.status.value?.running === true);
const blocked = computed(() => page.busy.value || running.value);
</script>

<template>
  <SectionShell :title="page.t('versionsTitle')">
    <template #actions>
      <span class="toggle">
        <span id="prereleases-label">{{ page.t("showPrereleases") }}</span>
        <BaseSwitch v-model="showPrereleases" aria-labelledby="prereleases-label" />
      </span>
    </template>

    <FactGrid :facts="facts" />

    <UpdateBand
      :check="page.check.value"
      :checking="page.checking.value"
      :disabled="page.busy.value"
      :verdict="verdict"
      :check-label="checkLabel"
      :check-action="page.t('checkNow')"
      :checking-label="page.t('checking')"
      :unknown-label="page.t('unknown')"
      :node-label="page.t('node')"
      :update-label="page.t('updateAvailable')"
      checkable
      @check="page.checkNow()"
    />

    <p v-if="running" class="note">{{ page.t("running") }}</p>

    <LoadingState v-if="!page.versions.value" :text="page.t('loading')" />
    <VersionRowList
      v-else
      :rows="rows"
      :source-key="`${page.status.value?.instanceId ?? ''}:${showPrereleases}`"
      :busy="blocked"
      fill
      :empty-text="page.t('noVersions')"
      :switch-label="page.t('switch')"
      :installed-label="page.t('installed')"
      :loading-label="page.t('loading')"
      @activate="page.switchTo($event)"
    />

    <p class="note">
      {{ page.t("registry") }}: {{ page.versions.value?.registry ?? "—" }}
    </p>
  </SectionShell>

  <SectionShell v-if="tagRows.length" :title="page.t('distTags')">
    <VersionRowList
      :rows="tagRows"
      :source-key="`tags:${page.status.value?.instanceId ?? ''}`"
      :busy="blocked"
      :switch-label="page.t('switch')"
      :installed-label="page.t('installed')"
      :loading-label="page.t('loading')"
      @activate="page.switchTo($event)"
    />
  </SectionShell>
</template>

<style scoped>
.toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--text-secondary);
  font: var(--type-caption);
}

.note {
  margin: 0;
  color: var(--text-secondary);
  font: var(--type-caption);
  overflow-wrap: anywhere;
}
</style>
