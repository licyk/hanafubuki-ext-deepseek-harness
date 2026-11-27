/** What the backend's frame calls answer, as `backend/main.py` reads them. */

/** Which Node.js an instance runs: the one this extension downloaded, the user's, or a global prefix's. */
export type NodeSource = "managed" | "own" | "prefix";

/** `status`: the instance as it stands, with the strings the page draws in. */
export interface Status {
  instanceId: string;
  running: boolean;
  installed: string | null;
  node: string | null;
  nodeSource: NodeSource;
  /** The `nodeVersion` the instance's install values ask for. */
  nodeVersion: string | null;
  nodePath: string;
  prefix: string | null;
  /** The instance's own dsh home; null for a global prefix, which uses ~/.dsh. */
  homePath: string | null;
  canCopyHome: boolean;
  copying: boolean;
  requested: { version: string | null; nodeVersion: string | null };
  locale: string;
  strings: Record<string, Record<string, string>>;
}

/** One published dsh, as the npm registry lists it. */
export interface PublishedVersion {
  version: string;
  published: string | null;
}

/** `versions`: the registry's catalogue, newest first. */
export interface Versions {
  registry: string;
  distTags: Record<string, string>;
  versions: PublishedVersion[];
}

/** One component an update would change: dsh, and the Node.js this extension downloads. */
export interface CheckedComponent {
  name: "core" | "node" | string;
  current: string | null;
  latest: string | null;
  hasUpdate: boolean;
}

/** `checkUpdate`: what an update would change, and what the update would be asked for. */
export interface UpdateCheck {
  current: string | null;
  latest: string | null;
  hasUpdate: boolean;
  components?: CheckedComponent[];
  checkedAt: string;
  requested: { version: string; nodeVersion: string };
  updatable: boolean;
  running: boolean;
}
