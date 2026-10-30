/** Only public asset URLs belong here; R2 upload credentials stay outside Vite. */
export function swatchAssetUrl(path: string, baseUrl = ''): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${baseUrl.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`;
}
