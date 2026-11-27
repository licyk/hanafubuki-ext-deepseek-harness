/**
 * The extension's management sections, one per frame page. Each is built
 * into its own `ui/<page>/` by `scripts/build-pages.ts`, which writes the
 * page into the entry HTML's `data-page`, and each is a `contributes.ui`
 * entry in the manifest.
 */

/** The pages, in the order the manifest lists them. */
export const PAGES = ["versions", "node", "configuration"] as const;

/** One of them. */
export type PageId = (typeof PAGES)[number];

/**
 * The page this bundle was built as. The build stamps it on the entry HTML
 * (`data-page`), so a page needs no guessing from its URL; an HTML that names
 * none — the source served by `npm run dev`, say — takes the first. Read from
 * the document at the call site, not on import: the build script imports this
 * module too, where there is no document to read.
 */
export function currentPage(): PageId {
  const named = document.documentElement.dataset.page;
  return PAGES.find((page) => page === named) ?? PAGES[0];
}
