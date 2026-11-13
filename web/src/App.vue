<script setup lang="ts">
// The instance's version page: what is installed, what npm offers, and a
// switch that asks the host to update the instance with another version;
// which Node.js it runs, and where dsh keeps its home (with the one-time
// copy of ~/.dsh). Everything comes from the backend through the frame
// client (`status`, `versions`, `copyHome`); the page has no network of its
// own. The controls are the application's own components, which the host
// serves every frame (`__hanafubuki/ui.js`, installed in main.ts).
import { computed, onMounted, ref } from "vue";
import * as client from "hanafubuki-frame";
import type { FrameError } from "hanafubuki-frame";
import { BaseInput, BaseSwitch, InfoBar, ProgressBar, RefreshButton, StatusBadge } from "hanafubuki-ui";

interface Status {
  running: boolean;
  installed: string | null;
  node: string | null;
  // `managed`: the Node.js the extension downloads; `own`: the user's, an
  // external `node`; `prefix`: a global npm prefix's, dsh included.
  nodeSource: "managed" | "own" | "prefix";
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

const SHOWN = 20;

const status = ref<Status | null>(null);
const versions = ref<Versions | null>(null);
const nodeVersion = ref("");
const showPrereleases = ref(true);
const showAll = ref(false);
const message = ref("");
const failed = ref(false);
const busy = ref(false);
const refreshing = ref(false);
// The application's language, which the host sends with the theme; the
// backend's answer stands in until it has.
const hostLocale = ref(client.locale());
client.onLocale((locale) => (hostLocale.value = locale));

const strings = computed(() => {
  const all = status.value?.strings ?? {};
  const locale = hostLocale.value ?? status.value?.locale ?? "en";
  const chosen = locale === "en" || locale === "zh" ? locale : navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
  return { ...all.en, ...all[chosen] };
});

function t(key: string, values: Record<string, string | number> = {}): string {
  const text = strings.value[key] ?? (key === "loading" ? "Loading…" : key);
  return text.replace(/\{(\w+)\}/g, (_, name: string) => String(values[name] ?? ""));
}

const listed = computed(() => {
  const all = (versions.value?.versions ?? []).filter((entry) => showPrereleases.value || !entry.version.includes("-"));
  return showAll.value ? all : all.slice(0, SHOWN);
});

const hidden = computed(() => {
  const all = (versions.value?.versions ?? []).filter((entry) => showPrereleases.value || !entry.version.includes("-"));
  return all.length > SHOWN && !showAll.value ? all.length : 0;
});

function published(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

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
    nodeVersion.value = status.value.requested.nodeVersion ?? nodeVersion.value;
    versions.value = await client.call<Versions>("versions", { refresh });
  } catch (error) {
    failed.value = true;
    message.value = describe(error);
  } finally {
    refreshing.value = false;
  }
}

async function update(values: { version?: string; nodeVersion?: string }): Promise<void> {
  busy.value = true;
  message.value = "";
  failed.value = false;
  try {
    const version = values.version ?? status.value?.requested.version ?? "latest";
    // A global prefix's type has no `nodeVersion`: its Node.js is the user's.
    await client.updateInstance(
      status.value?.nodeSource === "prefix"
        ? { version }
        : {
            version,
            nodeVersion: values.nodeVersion ?? (nodeVersion.value.trim() || status.value?.requested.nodeVersion || "24"),
          },
    );
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

onMounted(() => {
  client.ready();
  // The copy runs on in the backend; it says here when it is done.
  client.on("home-copied", (payload) => {
    const done = payload as { error?: string | null } | null;
    failed.value = Boolean(done?.error);
    void load().then(() => {
      if (done?.error) message.value = done.error;
    });
  });
  void load();
});
</script>

<template>
  <main class="page">
    <section class="summary">
      <div class="fact">
        <span class="label">{{ t("installed") }}</span>
        <span class="value mono">{{ status ? (status.installed ?? t("notInstalled")) : t("loading") }}</span>
      </div>
      <div class="fact">
        <span class="label">{{ t("node") }}</span>
        <span class="value mono">
          {{
            status
              ? status.nodeSource === "own"
                ? t("nodeOwn", { version: status.node ?? t("unknown") })
                : (status.node ?? t("unknown"))
              : "…"
          }}
        </span>
      </div>
      <div class="fact">
        <span class="label">{{ t("requested") }}</span>
        <span class="value mono">
          {{ status?.requested.version ?? "—" }} · Node.js {{ status?.requested.nodeVersion ?? "—" }}
        </span>
      </div>
      <RefreshButton class="refresh" :label="t('refresh')" :busy="refreshing" :disabled="busy" @click="load(true)" />
    </section>

    <!-- A bar comes and goes through `open`, which collapses it away. -->
    <InfoBar :open="Boolean(message)" :severity="failed ? 'error' : 'info'" :message="message" />
    <InfoBar :open="Boolean(status?.running)" severity="warning" :message="t('running')" />
    <p v-if="status && !status.running" class="hint">{{ t("confirmHint") }}</p>

    <section v-if="versions" class="block">
      <h2>{{ t("distTags") }}</h2>
      <ul class="card-list compact">
        <li v-for="(version, tag) in versions.distTags" :key="tag" class="card-row">
          <span class="card-row__text">
            <span class="card-row__title">{{ tag }}</span>
            <span class="card-row__description mono">{{ version }}</span>
          </span>
          <span class="card-row__control">
            <StatusBadge v-if="version === status?.installed" tone="success">{{ t("current") }}</StatusBadge>
            <button v-else type="button" class="btn btn-sm" :disabled="busy || status?.running" @click="update({ version: String(tag) })">
              {{ t("switch") }}
            </button>
          </span>
        </li>
      </ul>
    </section>

    <section v-if="versions" class="block">
      <div class="heading">
        <h2>{{ t("versions") }}</h2>
        <!-- The label is text, not a <label>: only the switch itself toggles. -->
        <span class="inline">
          <span id="prereleases-label">{{ t("showPrereleases") }}</span>
          <BaseSwitch v-model="showPrereleases" aria-labelledby="prereleases-label" />
        </span>
      </div>
      <ul class="card-list compact">
        <li v-for="entry in listed" :key="entry.version" class="card-row">
          <span class="card-row__text">
            <span class="card-row__title mono">{{ entry.version }}</span>
          </span>
          <span class="card-row__control">
            <span class="hint">{{ published(entry.published) }}</span>
            <StatusBadge v-if="entry.version === status?.installed" tone="success">{{ t("current") }}</StatusBadge>
            <button v-else type="button" class="btn btn-sm" :disabled="busy || status?.running" @click="update({ version: entry.version })">
              {{ t("switch") }}
            </button>
          </span>
        </li>
      </ul>
      <button v-if="hidden" type="button" class="btn btn-subtle show-all" @click="showAll = true">{{ t("showAll", { count: hidden }) }}</button>
      <p class="hint">{{ t("registry") }}: {{ versions.registry }}</p>
    </section>

    <section v-if="status?.nodeSource === 'prefix'" class="block">
      <h2>{{ t("nodeVersion") }}</h2>
      <p class="hint">{{ t("nodePrefix", { prefix: status.prefix ?? "" }) }}</p>
      <p class="hint">{{ t("nodeUnmanaged") }}</p>
    </section>
    <section v-else-if="status?.nodeSource === 'own'" class="block">
      <h2>{{ t("nodeVersion") }}</h2>
      <p class="hint">{{ t("nodeExternal", { path: status.nodePath }) }}</p>
    </section>
    <section v-else-if="status" class="block">
      <!-- The section's heading names the field: a FormField would repeat it as a label. -->
      <h2 id="node-version-label">{{ t("nodeVersion") }}</h2>
      <div class="inline">
        <BaseInput
          class="mono node-version"
          :model-value="nodeVersion"
          spellcheck="false"
          aria-labelledby="node-version-label"
          aria-describedby="node-version-help"
          @update:model-value="nodeVersion = String($event ?? '')"
        />
        <button type="button" class="btn btn-primary" :disabled="busy || status.running || !nodeVersion.trim()" @click="update({ nodeVersion: nodeVersion.trim() })">
          {{ t("apply") }}
        </button>
      </div>
      <p id="node-version-help" class="hint">{{ t("nodeVersionHelp") }}</p>
    </section>

    <section v-if="status" class="block">
      <h2>{{ t("home") }}</h2>
      <p>
        {{ status.homePath ? t("homeInstance", { path: status.homePath }) : t("homeUser") }}
      </p>
      <p v-if="status.homePath" class="hint">{{ t("homeHint") }}</p>
      <div v-if="status.canCopyHome" class="inline">
        <button type="button" class="btn" :disabled="busy || status.running || status.copying" @click="copyHome()">
          {{ t("copyHome") }}
        </button>
      </div>
      <ProgressBar v-if="status.copying" :value="null" :label="t('copyHome')" />
      <p v-if="status.canCopyHome" class="hint">{{ t("copyHomeHint") }}</p>
    </section>
  </main>
</template>
