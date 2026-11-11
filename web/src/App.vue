<script setup lang="ts">
// The instance's version page: what is installed, what npm offers, and a
// switch that asks the host to update the instance with another version.
// Everything comes from the backend through the frame client (`status`,
// `versions`); the page has no network of its own.
import { computed, onMounted, ref } from "vue";
import * as client from "hanafubuki-frame";
import type { FrameError } from "hanafubuki-frame";

interface Status {
  running: boolean;
  installed: string | null;
  node: string | null;
  // False for a global npm prefix: its Node.js is the user's.
  nodeManaged: boolean;
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

const strings = computed(() => {
  const all = status.value?.strings ?? {};
  const locale = status.value?.locale ?? "en";
  const chosen = locale === "en" || locale === "zh" ? locale : navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
  return { ...all.en, ...all[chosen] };
});

function t(key: string, values: Record<string, string | number> = {}): string {
  const text = strings.value[key] ?? (key === "loading" ? "Loading…" : key);
  return text.replace(/\{(\w+)\}/g, (_, name: string) => String(values[name] ?? ""));
}

const canUpdate = computed(() => typeof client.updateInstance === "function");

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
  try {
    status.value = await client.call<Status>("status");
    nodeVersion.value = status.value.requested.nodeVersion ?? nodeVersion.value;
  } catch (error) {
    failed.value = true;
    message.value = describe(error);
    return;
  }
  try {
    versions.value = await client.call<Versions>("versions", { refresh });
  } catch (error) {
    failed.value = true;
    message.value = describe(error);
  }
}

async function update(values: { version?: string; nodeVersion?: string }): Promise<void> {
  if (!client.updateInstance) return;
  busy.value = true;
  message.value = "";
  failed.value = false;
  try {
    await client.updateInstance({
      version: values.version ?? status.value?.requested.version ?? "latest",
      nodeVersion: values.nodeVersion ?? (nodeVersion.value.trim() || status.value?.requested.nodeVersion || "24"),
    });
    message.value = t("started");
  } catch (error) {
    failed.value = true;
    message.value = describe(error);
  } finally {
    busy.value = false;
  }
}

onMounted(() => {
  client.ready();
  void load();
});
</script>

<template>
  <main class="page">
    <section class="summary">
      <div class="fact">
        <span class="label">{{ t("installed") }}</span>
        <span class="value">{{ status ? (status.installed ?? t("notInstalled")) : t("loading") }}</span>
      </div>
      <div class="fact">
        <span class="label">{{ t("node") }}</span>
        <span class="value">{{ status ? (status.node ?? t("unknown")) : "…" }}</span>
      </div>
      <div class="fact">
        <span class="label">{{ t("requested") }}</span>
        <span class="value">
          {{ status?.requested.version ?? "—" }} · Node.js {{ status?.requested.nodeVersion ?? "—" }}
        </span>
      </div>
      <button type="button" class="button" :disabled="busy" @click="load(true)">{{ t("refresh") }}</button>
    </section>

    <p v-if="message" class="message" :class="{ error: failed }" role="status">{{ message }}</p>
    <p v-if="status && !canUpdate" class="message warning">{{ t("unsupported") }}</p>
    <p v-else-if="status?.running" class="message warning">{{ t("running") }}</p>
    <p v-else-if="status" class="hint">{{ t("confirmHint") }}</p>

    <section v-if="versions" class="block">
      <h2>{{ t("distTags") }}</h2>
      <ul class="rows">
        <li v-for="(version, tag) in versions.distTags" :key="tag" class="row">
          <span class="name">{{ tag }}</span>
          <span class="detail">{{ version }}</span>
          <span v-if="version === status?.installed" class="current">{{ t("current") }}</span>
          <button v-else type="button" class="button" :disabled="!canUpdate || busy || status?.running" @click="update({ version: String(tag) })">
            {{ t("switch") }}
          </button>
        </li>
      </ul>
    </section>

    <section v-if="versions" class="block">
      <div class="heading">
        <h2>{{ t("versions") }}</h2>
        <label class="toggle"><input v-model="showPrereleases" type="checkbox" /> {{ t("showPrereleases") }}</label>
      </div>
      <ul class="rows">
        <li v-for="entry in listed" :key="entry.version" class="row">
          <span class="name mono">{{ entry.version }}</span>
          <span class="detail">{{ published(entry.published) }}</span>
          <span v-if="entry.version === status?.installed" class="current">{{ t("current") }}</span>
          <button v-else type="button" class="button" :disabled="!canUpdate || busy || status?.running" @click="update({ version: entry.version })">
            {{ t("switch") }}
          </button>
        </li>
      </ul>
      <button v-if="hidden" type="button" class="link" @click="showAll = true">{{ t("showAll", { count: hidden }) }}</button>
      <p class="hint">{{ t("registry") }}: {{ versions.registry }}</p>
    </section>

    <section v-if="status && !status.nodeManaged" class="block">
      <h2>{{ t("nodeVersion") }}</h2>
      <p class="hint">{{ t("nodeUnmanaged") }}</p>
    </section>
    <section v-else-if="status" class="block">
      <h2>{{ t("nodeVersion") }}</h2>
      <div class="inline">
        <input v-model="nodeVersion" class="input mono" type="text" spellcheck="false" :aria-label="t('nodeVersion')" />
        <button type="button" class="button accent" :disabled="!canUpdate || busy || status.running || !nodeVersion.trim()" @click="update({ nodeVersion: nodeVersion.trim() })">
          {{ t("apply") }}
        </button>
      </div>
      <p class="hint">{{ t("nodeVersionHelp") }}</p>
    </section>
  </main>
</template>
