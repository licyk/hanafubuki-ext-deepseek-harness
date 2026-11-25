<script setup lang="ts">
// The instance's version page, built the way the application's own version
// panel is: the facts of what is installed, one row per version that carries
// its own switch action, and the installed row marked in place. Everything
// comes from the backend through the frame client (`status`, `versions`,
// `copyHome`); the page has no network of its own.
//
// The Node.js version is not a control here. `nodeVersion` is one of the
// type's install parameters, so the maintenance panel's install form is where
// it changes; this page reports which Node.js runs and what its values ask
// for. A switch therefore asks the host to update the instance with the
// version alone (`updateInstance`), which keeps that recorded `nodeVersion`.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as client from "hanafubuki-frame";
import type { FrameError } from "hanafubuki-frame";
import {
  BaseSwitch,
  EmptyState,
  InfoBar,
  LoadingState,
  ProgressBar,
  RefreshButton,
  StatusBadge,
  UpdateHint,
} from "hanafubuki-ui";

interface Status {
  running: boolean;
  installed: string | null;
  node: string | null;
  // `managed`: the Node.js the extension downloads; `own`: the user's, an
  // external `node`; `prefix`: a global npm prefix's, dsh included.
  nodeSource: "managed" | "own" | "prefix";
  // The `nodeVersion` the instance's install values ask for.
  nodeVersion: string | null;
  nodePath: string;
  prefix: string | null;
  // The instance's own dsh home; null for a global prefix, which uses ~/.dsh.
  homePath: string | null;
  canCopyHome: boolean;
  copying: boolean;
  requested: { version: string | null; nodeVersion: string | null };
  locale: string;
  strings: Record<string, Record<string, string>>;
}

interface Versions {
  registry: string;
  distTags: Record<string, string>;
  versions: { version: string; published: string | null }[];
}

/** What an update would change, as the backend's update check reports it. */
interface UpdateCheck {
  current: string | null;
  latest: string | null;
  hasUpdate: boolean;
  notes?: string | null;
  components?: { name: string; current: string | null; latest: string | null; hasUpdate: boolean }[];
  checkedAt: string;
  requested: { version: string; nodeVersion: string };
  updatable: boolean;
  running: boolean;
}

// The list reveals itself in batches, so a registry with hundreds of versions
// does not paint them all: the sentinel row asks for the next batch.
const BATCH = 50;

const status = ref<Status | null>(null);
const versions = ref<Versions | null>(null);
const showPrereleases = ref(true);
const shown = ref(BATCH);
const message = ref("");
const failed = ref(false);
// What the bar shows: kept while it closes, so it collapses with the text and
// severity it had rather than an empty info bar.
const bar = ref<{ text: string; severity: "info" | "error" }>({ text: "", severity: "info" });
watch([message, failed], ([text, isFailed]) => {
  if (text) bar.value = { text, severity: isFailed ? "error" : "info" };
});
const busy = ref(false);
const refreshing = ref(false);
// The update check's last answer, and whether one is in flight.
const check = ref<UpdateCheck | null>(null);
const checking = ref(false);
const sentinel = ref<HTMLElement | null>(null);
let observer: IntersectionObserver | null = null;
// The application's language, which the host sends with the theme; the
// backend's answer stands in until it has.
const hostLocale = ref(client.locale());
client.onLocale((locale) => (hostLocale.value = locale));

const strings = computed(() => {
  const all = status.value?.strings ?? {};
  const locale = hostLocale.value ?? status.value?.locale ?? "en";
  const chosen =
    locale === "en" || locale === "zh"
      ? locale
      : navigator.language.toLowerCase().startsWith("zh")
        ? "zh"
        : "en";
  return { ...all.en, ...all[chosen] };
});

function t(key: string, values: Record<string, string | number> = {}): string {
  const text = strings.value[key] ?? (key === "loading" ? "Loading…" : key);
  return text.replace(/\{(\w+)\}/g, (_, name: string) => String(values[name] ?? ""));
}

/** The versions to show, newest first, pre-releases filtered as asked. */
const available = computed(() =>
  (versions.value?.versions ?? []).filter(
    (entry) => showPrereleases.value || !entry.version.includes("-"),
  ),
);

const listed = computed(() => available.value.slice(0, shown.value));
const hasMore = computed(() => available.value.length > listed.value.length);

/** The `latest` dist-tag, which the list marks as it does its own. */
const latest = computed(() => versions.value?.distTags?.latest ?? null);

function published(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

/** When the check answered, in the reader's own time. */
function checkedAt(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

/** The verdict of the check, as one line. */
const verdict = computed(() => {
  const found = check.value;
  if (!found) return "";
  if (!found.hasUpdate) return t("checkUpToDate");
  const update = found.components?.find((part) => part.name === "core");
  const from = update?.current ?? found.current ?? "—";
  const to = update?.latest ?? found.latest ?? "—";
  return t("checkUpdateAvailable", { current: from, latest: to });
});

function describe(error: unknown): string {
  const failure = error as Partial<FrameError>;
  return failure?.message ? `${failure.kind ?? "failed"}: ${failure.message}` : String(error);
}

async function load(refresh = false): Promise<void> {
  message.value = "";
  failed.value = false;
  refreshing.value = true;
  try {
    status.value = await client.call<Status>("status");
    versions.value = await client.call<Versions>("versions", { refresh });
    shown.value = BATCH;
    // The page's own check follows the refresh: a version published since
    // the last answer is what the reader refreshed to see.
    await updateCheck(refresh);
  } catch (error) {
    failed.value = true;
    message.value = describe(error);
  } finally {
    refreshing.value = false;
  }
}

/**
 * Asks the backend what an update would change: the dsh the instance has
 * against the one its `version` value names, and the Node.js its
 * `nodeVersion` names. `refresh` re-reads the registry instead of its cache.
 */
async function updateCheck(refresh = false): Promise<void> {
  checking.value = true;
  try {
    check.value = await client.call<UpdateCheck>("checkUpdate", { refresh });
  } catch (error) {
    // A check that cannot answer leaves the rest of the page as it is: the
    // catalogue and the switch actions do not depend on it.
    check.value = null;
    failed.value = true;
    message.value = describe(error);
  } finally {
    checking.value = false;
  }
}

/**
 * Switches the instance to `version` (a version or a dist-tag). Only the
 * version travels: the recorded `nodeVersion` stays as the maintenance panel
 * left it, so a switch never moves the Node.js by accident.
 */
async function switchTo(version: string): Promise<void> {
  busy.value = true;
  message.value = "";
  failed.value = false;
  try {
    await client.updateInstance({ version });
    message.value = t("started");
  } catch (error) {
    failed.value = true;
    message.value = describe(error);
  } finally {
    busy.value = false;
  }
}

async function copyHome(): Promise<void> {
  busy.value = true;
  message.value = "";
  failed.value = false;
  try {
    const answer = await client.call<{ notice: string }>("copyHome");
    message.value = answer.notice;
    if (status.value) status.value.copying = true;
  } catch (error) {
    failed.value = true;
    message.value = describe(error);
  } finally {
    busy.value = false;
  }
}

function revealMore(): void {
  shown.value += BATCH;
}

/** The bar's one manual check: the registry is read again, not its cache. */
async function checkNow(): Promise<void> {
  message.value = "";
  failed.value = false;
  await updateCheck(true);
}

onMounted(() => {
  client.ready();
  client.onLocale((locale) => (hostLocale.value = locale));
  // The copy runs on in the backend; it says here when it is done.
  client.on("home-copied", (payload) => {
    const done = payload as { error?: string | null } | null;
    failed.value = Boolean(done?.error);
    void load().then(() => {
      if (done?.error) message.value = done.error;
    });
  });
  // A sentinel below the list asks for the next batch as it nears the page.
  observer = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting) && hasMore.value) revealMore();
  });
  watch(sentinel, (element) => {
    observer?.disconnect();
    if (element) observer?.observe(element);
  });
  void load();
});

onBeforeUnmount(() => observer?.disconnect());
</script>

<template>
  <main class="page">
    <!-- What is installed, the way the version panel states it: a labelled
         row of facts, with the section's one refresh at the trailing end. -->
    <section class="facts">
      <div class="fact">
        <span class="fact__label">{{ t("installed") }}</span>
        <span class="fact__value mono">{{
          status ? (status.installed ?? t("notInstalled")) : t("loading")
        }}</span>
      </div>
      <div class="fact">
        <span class="fact__label">{{ t("node") }}</span>
        <span class="fact__value mono">{{
          status
            ? status.nodeSource === "own"
              ? t("nodeOwn", { version: status.node ?? t("unknown") })
              : (status.node ?? t("unknown"))
            : t("loading")
        }}</span>
      </div>
      <div class="fact">
        <span class="fact__label">{{ t("requestedVersion") }}</span>
        <span class="fact__value mono">{{ status?.requested.version ?? "—" }}</span>
      </div>
      <div class="fact">
        <span class="fact__label">{{ t("requestedNode") }}</span>
        <span class="fact__value mono">{{ status?.nodeVersion ?? t("nodeFromInstall") }}</span>
      </div>
      <RefreshButton
        class="facts__refresh"
        :label="t('refresh')"
        :busy="refreshing"
        :disabled="busy"
        @click="load(true)"
      />
    </section>

    <!-- What an update would change: the answer to the page's own check,
         dated, with the components beside it. -->
    <section class="band">
      <div class="band__verdict">
        <StatusBadge
          v-if="check"
          :tone="check.hasUpdate ? 'warning' : 'success'"
          :dot="checking"
          :pulse="checking"
        >
          {{ verdict }}
        </StatusBadge>
        <span v-else class="note">{{ t("checkNotRun") }}</span>
        <span v-if="check" class="band__time">
          {{ t("checkedAt", { time: checkedAt(check.checkedAt) }) }}
        </span>
      </div>
      <div class="band__actions">
        <UpdateHint v-if="check?.hasUpdate" :text="verdict" :label="t('updateAvailable')" />
        <button type="button" class="btn btn-sm" :disabled="checking || busy" @click="checkNow()">
          {{ checking ? t("checking") : t("checkNow") }}
        </button>
      </div>
      <dl v-if="check?.components?.length" class="pairs band__parts">
        <template v-for="part in check.components" :key="part.name">
          <dt>{{ t(`component_${part.name}`) }}</dt>
          <dd>
            <span class="mono">{{
              [part.current, part.latest !== part.current ? part.latest : null]
                .filter(Boolean)
                .join(" → ") || "—"
            }}</span>
            {{ t(part.hasUpdate ? "updateAvailable" : "upToDate") }}
          </dd>
        </template>
      </dl>
    </section>

    <!-- A bar comes and goes through `open`, which collapses it away. -->
    <InfoBar :open="Boolean(message)" :severity="bar.severity" :message="bar.text" />
    <InfoBar :open="Boolean(status?.running)" severity="warning" :message="t('running')" />
    <p v-if="status && !status.running" class="note">{{ t("confirmHint") }}</p>

    <!-- The published set, one row per version. -->
    <section class="group">
      <div class="group__heading">
        <h2 class="group__title">{{ t("versions") }}</h2>
        <!-- The label is text, not a <label>: only the switch itself toggles. -->
        <span class="toggle">
          <span id="prereleases-label">{{ t("showPrereleases") }}</span>
          <BaseSwitch v-model="showPrereleases" aria-labelledby="prereleases-label" />
        </span>
      </div>

      <LoadingState v-if="!versions && !failed" :text="t('loading')" />

      <ul v-else-if="listed.length" class="versions">
        <li
          v-for="entry in listed"
          :key="entry.version"
          class="versions__row"
          :aria-current="entry.version === status?.installed ? 'true' : undefined"
        >
          <div class="versions__info">
            <code class="versions__id">{{ entry.version }}</code>
            <span v-if="entry.version === latest" class="versions__badges">
              <StatusBadge>{{ t("latest") }}</StatusBadge>
            </span>
            <span v-if="entry.version.includes('-')" class="versions__badges">
              <StatusBadge tone="neutral">{{ t("prerelease") }}</StatusBadge>
            </span>
          </div>
          <div class="versions__action">
            <span class="versions__date">{{ published(entry.published) }}</span>
            <StatusBadge v-if="entry.version === status?.installed" tone="accent">
              {{ t("current") }}
            </StatusBadge>
            <!-- One per row, so not a primary action. -->
            <button
              v-else
              type="button"
              class="btn btn-sm"
              :disabled="busy || status?.running"
              :title="t('switchTo', { version: entry.version })"
              @click="switchTo(entry.version)"
            >
              {{ t("switch") }}
            </button>
          </div>
        </li>
      </ul>

      <EmptyState v-else :text="t('noVersions')" />

      <!-- Reveals the next batch as it nears the page. -->
      <div v-if="hasMore" ref="sentinel" class="sentinel">
        <LoadingState :text="t('loading')" :size="16" />
      </div>
      <p class="note">{{ t("registry") }}: {{ versions?.registry ?? "—" }}</p>
    </section>

    <!-- The dist-tags, which a switch may name instead of a version. -->
    <section v-if="versions && Object.keys(versions.distTags).length" class="group">
      <h2 class="group__title">{{ t("distTags") }}</h2>
      <ul class="versions">
        <li v-for="(version, tag) in versions.distTags" :key="tag" class="versions__row">
          <div class="versions__info">
            <span class="versions__id">{{ tag }}</span>
            <span class="versions__badges">
              <StatusBadge tone="neutral">{{ version }}</StatusBadge>
            </span>
          </div>
          <div class="versions__action">
            <StatusBadge v-if="version === status?.installed" tone="accent">
              {{ t("current") }}
            </StatusBadge>
            <button
              v-else
              type="button"
              class="btn btn-sm"
              :disabled="busy || status?.running"
              :title="t('switchTo', { version })"
              @click="switchTo(String(tag))"
            >
              {{ t("switch") }}
            </button>
          </div>
        </li>
      </ul>
    </section>

    <!-- Where the versions run: reported, not chosen. -->
    <section v-if="status" class="group">
      <h2 class="group__title">{{ t("home") }}</h2>
      <dl class="pairs">
        <dt>{{ t("node") }}</dt>
        <dd class="mono">{{ status.nodePath }}</dd>
        <dt>{{ t("home") }}</dt>
        <dd>{{ status.homePath ?? t("homeUser") }}</dd>
      </dl>
      <p v-if="status.homePath" class="note">{{ t("homeHint") }}</p>
      <p v-if="status.nodeSource === 'prefix'" class="note">
        {{ t("nodePrefix", { prefix: status.prefix ?? "" }) }}
      </p>
      <p v-else-if="status.nodeSource === 'own'" class="note">
        {{ t("nodeExternal", { path: status.nodePath }) }}
      </p>
      <p v-else class="note">{{ t("nodeManaged", { version: status.nodeVersion ?? "—" }) }}</p>
      <p class="note">{{ t("nodeMaintenance") }}</p>
      <div v-if="status.canCopyHome" class="actions">
        <button
          type="button"
          class="btn"
          :disabled="busy || status.running || status.copying"
          @click="copyHome()"
        >
          {{ t("copyHome") }}
        </button>
      </div>
      <ProgressBar v-if="status.copying" :value="null" :label="t('copyHome')" />
      <p v-if="status.canCopyHome" class="note">{{ t("copyHomeHint") }}</p>
    </section>
  </main>
</template>

<style scoped>
/* The page is one column of groups, 12 apart (the application's section
   spacing), with each group's heading 8 above what it holds. */
.page {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3);
}

/* The facts: labelled values over one line, the refresh at the trailing end. */
.facts {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--space-3) var(--space-6);
}

.fact {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.fact__label {
  color: var(--text-secondary);
  font: var(--type-caption-strong);
}

/* The pair rather than `--type-body`, which would also reset `.mono`. */
.fact__value {
  font-size: var(--font-size-body);
  line-height: var(--line-height-body);
  overflow-wrap: anywhere;
  user-select: text;
}

.facts__refresh {
  margin-left: auto;
}

/* The update check: its verdict and when it answered, the control that runs
   it again, and the components the verdict is made of. */
.band {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--stroke-card);
  border-radius: var(--radius-control);
}

.band__verdict {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

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
  gap: var(--space-1) var(--space-3);
  font: var(--type-caption);
}

.group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
}

.group__heading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2) var(--space-3);
}

.group__title {
  margin: 0;
  font: var(--type-body-strong);
}

.toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--text-secondary);
  font: var(--type-caption);
}

/* The version rows: ruled, one per version, the action at the trailing end,
   as the application's own version list draws them. */
.versions {
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
  border: 1px solid var(--stroke-card);
  border-radius: var(--radius-control);
  grid-auto-rows: max-content;
  align-content: start;
}

.versions__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-3);
  min-height: 48px;
  padding: var(--space-1) var(--space-2);
}

.versions__row + .versions__row {
  border-top: 1px solid var(--stroke-divider);
}

.versions__info {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-1) var(--space-2);
  min-width: 0;
  padding: var(--space-0-5) var(--space-1);
}

.versions__id {
  min-width: 0;
  font-family: var(--font-mono);
  font-size: var(--font-size-body);
  line-height: var(--line-height-body);
  overflow-wrap: anywhere;
  user-select: text;
}

.versions__badges {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.versions__action {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-2);
}

.versions__date {
  color: var(--text-secondary);
  font: var(--type-caption);
  white-space: nowrap;
}

.pairs {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: var(--space-2) var(--space-3);
  margin: 0;
  font: var(--type-body);
}

.pairs dt {
  color: var(--text-secondary);
}

.pairs dd {
  margin: 0;
  overflow-wrap: anywhere;
  user-select: text;
}

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

.sentinel {
  display: flex;
  justify-content: center;
  padding: var(--space-2);
}

.mono {
  font-family: var(--font-mono);
}
</style>
