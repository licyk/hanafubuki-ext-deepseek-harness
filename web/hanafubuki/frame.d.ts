/**
 * The Hanafubuki frame client, version 1: what an extension's frame page
 * imports from `__hanafubuki/frame.js` at its package's root, by a relative
 * URL (`../__hanafubuki/frame.js` from `ui/index.html`). These typings are
 * the application repository's `sdk/frame/frame.d.ts`; an extension refers
 * to them (a `paths` entry or a declaration for the relative import) rather
 * than writing its own.
 */

/**
 * Why a call failed: the bridge's error type, or for {@link state} the
 * extension UI's own (`forbidden` too). The host's own requests fail
 * `invalid` (asked where they do not apply, or with members that do not
 * read) or `failed` (the user declined, or the application refused).
 */
export type FrameErrorKind = "unavailable" | "timeout" | "invalid" | "forbidden" | "failed";

/** A call's failure, as `call` rejects with it. */
export interface FrameError extends Error {
  name: "FrameError";
  kind: FrameErrorKind;
}

/**
 * Tells the host the page is ready. Until it does, the host shows nothing;
 * one that never does is unavailable after a few seconds. From then on the
 * host sends the theme and the application's language, and follows the
 * page's height. The client applies the theme to the page's root
 * (`data-theme`, `color-scheme` and the tokens as CSS variables, which the
 * UI kit `__hanafubuki/ui.css` reads) and the language to its `lang`.
 */
export function ready(): void;

/**
 * The application's language (`en`, `zh`; the root's `lang` too), or `null`
 * until the host has sent the theme, which it does once the page is
 * {@link ready}.
 */
export function locale(): string | null;

/**
 * Listens to the application's language: called when the host first sends
 * it and on each change after; returns how to stop listening.
 */
export function onLocale(listener: (locale: string) => void): () => void;

/**
 * Calls `method` of the extension's backend (`ui.frame.call`, within its
 * 30 s bound) and resolves with what it answered; rejects with a
 * {@link FrameError}. A data-only extension's frame has no backend: every
 * call fails `unavailable`.
 */
export function call<T = unknown>(method: string, params?: unknown): Promise<T>;

/**
 * Listens to `event`, which the backend sends this frame
 * (`ui.frame.emit`); returns how to stop listening.
 */
export function on<T = unknown>(event: string, listener: (payload: T) => void): () => void;

/**
 * Reads the state of the extension's UI (`ui.state`, with the frame's
 * context; within 10 s) and resolves with it; rejects with a
 * {@link FrameError}. Only a backend that announces the hook `ui` has one:
 * otherwise it fails `unavailable`.
 */
export function state<T = unknown>(): Promise<T>;

/** The extension's current stored setting overrides, validated by the host. */
export interface SettingsResult {
  values: Record<string, unknown>;
}

/** Reads this frame owner's settings; works without an extension backend. */
export function getSettings(): Promise<SettingsResult>;

/**
 * Patches this frame owner's declared settings through the host's validation
 * and persistence. A null value removes that override. Returns all stored
 * values after the write; works without an extension backend.
 */
export function patchSettings(patch: Record<string, unknown>): Promise<SettingsResult>;

/**
 * Listens to each state the extension's UI pushes (`ui.emit`, the last of
 * those within 100 ms); returns how to stop listening. A push is the whole
 * state, the same for every frame and panel of the extension. Read
 * {@link state} once as well: a state pushed before the page listened is
 * not sent again.
 */
export function onState<T = unknown>(listener: (state: T) => void): () => void;

/**
 * Opens the application's folder dialog, titled `title` (cut at 200
 * characters), and resolves with the native path the user chose, or `null`
 * when they cancelled. The page is given the path alone: it cannot read the
 * folder, and only its backend acts on it.
 */
export function pickDirectory(options?: { title?: string }): Promise<string | null>;

/**
 * Updates or reinstalls the frame's instance after confirmation, with up
 * to 64 install values replacing the recorded ones. When mode is omitted,
 * a ready type with update steps is updated; other types reinstall in
 * place. Rust validates the merged values. Resolves once it has started;
 * its progress is the instance's install progress. Rejects with a
 * {@link FrameError} of kind `invalid` outside an instance's management
 * section, and `failed` when the user declines, another update is waiting
 * for an answer, or the application refuses it.
 */
export function updateInstance(
  values: Record<string, unknown>,
  mode?: "update" | "reinstall",
): Promise<void>;

/**
 * Takes the user to an instance's page (`/instances/<instanceId>`), as a
 * downloader does after registering one; resolves once the application is
 * on its way there, which may close the frame.
 */
export function navigateInstance(instanceId: string): Promise<void>;

/** Opens a currently registered settings section. Unknown sections reject with FrameError. */
export function openSettings(section: string): Promise<void>;

/** Opens an HTTP(S) URL in the system browser. Rust validates it; invalid URLs or opener failures reject. */
export function openExternal(url: string): Promise<void>;

/**
 * Opens one of this extension's `dialogs` frames (`kind = "frame"`,
 * `slot = "dialogs"`) in a dialog over the window, titled `title` or by the
 * frame's own title. Resolves with what that page's {@link closeDialog}
 * gave, or `null` when the user dismissed it. Rejects `invalid` for a frame
 * that is not one of the extension's `dialogs` frames, and `failed` while
 * another dialog is open.
 */
export function openDialog<T = unknown>(
  frame: string,
  options?: { title?: string },
): Promise<T | null>;

/**
 * From a `dialogs` frame: closes its dialog, resolving the opener's
 * {@link openDialog} with `result` (any JSON under 64 KiB). Ignored in any
 * other frame.
 */
export function closeDialog(result?: unknown): void;

/**
 * From a frame in the install wizard (`[[install.frames]]` of an instance
 * type): merges `values` into the install form's draft as if the user
 * typed them, so the wizard's own validation and Rust's apply; keys the
 * type's install form does not declare are dropped, at most 64 kept.
 * Resolves once merged; rejects `invalid` elsewhere.
 */
export function setInstallValues(values: Record<string, unknown>): Promise<void>;

/**
 * Brings one of this extension's Task Center tabs (`taskCenter.tabs`) forward
 * by the panel's or frame's own id, opening the Task Center if it is closed.
 * Resolves once it is selected; rejects `invalid` for a tab the application
 * does not list for this extension.
 */
export function openTaskCenterTab(tab: string): Promise<void>;

/**
 * From a Task Center tab's frame: called each time that tab becomes the shown
 * one, `tab` its own id, so the page refreshes what it shows without
 * polling; returns how to stop listening.
 */
export function onTaskCenterTabShown(listener: (tab: string) => void): () => void;
