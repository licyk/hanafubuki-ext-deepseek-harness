/**
 * The version page's state, shared by its views: what the backend answered,
 * what is in flight, and the three things the page can ask it to do. Every
 * view reads the same instance, so the page has one store rather than one
 * per view — a refresh on the versions page is a refresh everywhere.
 */

import { computed, ref } from "vue";
import * as client from "hanafubuki-frame";
import type { FrameError } from "hanafubuki-frame";

import type { Status, UpdateCheck, Versions } from "../types";

/** How a failure reads: its kind, then what the host said. */
export function describeFailure(error: unknown): string {
  const failure = error as Partial<FrameError>;
  return failure?.message ? `${failure.kind ?? "failed"}: ${failure.message}` : String(error);
}

const status = ref<Status | null>(null);
const versions = ref<Versions | null>(null);
const check = ref<UpdateCheck | null>(null);

const loading = ref(false);
const refreshing = ref(false);
const checking = ref(false);
const busy = ref(false);

/** The page's message, and whether it reports a failure rather than an outcome. */
const message = ref("");
const failed = ref(false);
/** What the last action was about, so a view can say where its failure came from. */
const scope = ref<"status" | "versions" | "check" | "action">("status");

let loaded = false;

function report(text: string, isFailure = false, from: typeof scope.value = "action"): void {
  message.value = text;
  failed.value = isFailure;
  scope.value = from;
}

/** `status`: what the instance runs, and its homes. */
async function readStatus(): Promise<void> {
  status.value = await client.call<Status>("status");
}

/** `versions`: the registry's catalogue, re-read when `refresh` asks for it. */
async function readVersions(refresh = false): Promise<void> {
  versions.value = await client.call<Versions>("versions", { refresh });
}

/**
 * `checkUpdate`: what an update would change. A check that cannot answer
 * leaves the rest of the page as it is — the catalogue and the switch
 * actions do not depend on it — so its failure is reported where the answer
 * would have been, not as a page-level error.
 */
async function readCheck(refresh = false): Promise<void> {
  checking.value = true;
  try {
    check.value = await client.call<UpdateCheck>("checkUpdate", { refresh });
  } catch (error) {
    check.value = null;
    report(describeFailure(error), true, "check");
  } finally {
    checking.value = false;
  }
}

/** Everything, without a word about it: what the page does when it opens. */
async function load(): Promise<void> {
  loading.value = true;
  message.value = "";
  failed.value = false;
  try {
    await readStatus();
    await readVersions();
    await readCheck();
    loaded = true;
  } catch (error) {
    report(describeFailure(error), true, status.value ? "versions" : "status");
  } finally {
    loading.value = false;
  }
}

/** The page's one refresh: the registry is read again, not its cache. */
async function refresh(): Promise<void> {
  refreshing.value = true;
  message.value = "";
  failed.value = false;
  try {
    await readStatus();
    await readVersions(true);
    await readCheck(true);
  } catch (error) {
    report(describeFailure(error), true, status.value ? "versions" : "status");
  } finally {
    refreshing.value = false;
  }
}

/** The check on its own, which the versions view offers beside its verdict. */
async function checkNow(): Promise<void> {
  message.value = "";
  failed.value = false;
  await readCheck(true);
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
    report(strings.value.started);
  } catch (error) {
    report(describeFailure(error), true, "action");
  } finally {
    busy.value = false;
  }
}

/** `copyHome`: copies the user's ~/.dsh and ~/.agents in, on a thread of the backend's own. */
async function copyHome(): Promise<void> {
  busy.value = true;
  message.value = "";
  failed.value = false;
  try {
    const answer = await client.call<{ notice: string }>("copyHome");
    report(answer.notice);
    if (status.value) status.value.copying = true;
  } catch (error) {
    report(describeFailure(error), true, "action");
  } finally {
    busy.value = false;
  }
}

// The application's language, which the host sends with the theme; the
// backend's answer stands in until it has.
const hostLocale = ref<string | null>(client.locale());
client.onLocale((locale) => (hostLocale.value = locale));

const locale = computed(() => {
  const chosen = hostLocale.value ?? status.value?.locale ?? "en";
  if (chosen === "en" || chosen === "zh") return chosen;
  return navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
});

/** The backend's page strings, in the language the host is in. */
const strings = computed<Record<string, string>>(() => {
  const all = status.value?.strings ?? {};
  return { ...all.en, ...all[locale.value] };
});

function t(key: string, values: Record<string, string | number> = {}): string {
  const text = strings.value[key] ?? (key === "loading" ? "Loading…" : key);
  return text.replace(/\{(\w+)\}/g, (_, name: string) => String(values[name] ?? ""));
}

export function useVersionPage() {
  return {
    status,
    versions,
    check,
    loading,
    refreshing,
    checking,
    busy,
    message,
    failed,
    scope,
    locale,
    strings,
    loaded,
    t,
    load,
    refresh,
    checkNow,
    switchTo,
    copyHome,
    readStatus,
    report,
  };
}

/** Whether the page has read anything yet: the views wait for it together. */
export const pageReady = computed(() => status.value !== null);

