// The Hanafubuki frame client (`__hanafubuki/frame.js`, typed by the
// application's `sdk/frame/frame.d.ts`), imported as `hanafubuki-frame`;
// the build rewrites the import to the client's relative URL.
declare module "hanafubuki-frame" {
  export type FrameErrorKind = "unavailable" | "timeout" | "invalid" | "forbidden" | "failed";

  export interface FrameError extends Error {
    name: "FrameError";
    kind: FrameErrorKind;
  }

  export function ready(): void;
  export function call<T = unknown>(method: string, params?: unknown): Promise<T>;
  export function on<T = unknown>(event: string, listener: (payload: T) => void): () => void;
  export function state<T = unknown>(): Promise<T>;
  export function onState<T = unknown>(listener: (state: T) => void): () => void;
  /** Newer hosts only: reinstall the frame's instance with replacement values, once the user confirms. */
  export const updateInstance: ((values: Record<string, unknown>) => Promise<void>) | undefined;
}

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<object, object, unknown>;
  export default component;
}
