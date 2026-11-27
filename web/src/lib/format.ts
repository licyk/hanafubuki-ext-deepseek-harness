/** How many rows a version list paints at a time, as the application's own lists do. */
export const VERSION_BATCH = 50;

/** When a version was published, in the reader's own date format. */
export function publishedDate(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

/** When the update check answered, in the reader's own date and time. */
export function localDateTime(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

/** Whether a version is a pre-release, which the list marks with its own pill. */
export function isPrerelease(version: string): boolean {
  return version.includes("-");
}
