/** One image resource per sheet URL, scoped to a mounted Pattern panel. */
export class PieceImageCache {
  constructor(
    private createImage: () => HTMLImageElement = () => new Image(),
  ) {}
  retain(urls: Set<string>) {
    for (const [url, entry] of this.entries) {
      if (!urls.has(url)) {
        entry.image.onload = null;
        this.entries.delete(url);
      }
    }
  }
  private entries = new Map<
    string,
    { image: HTMLImageElement; ready: boolean; listeners: Set<() => void> }
  >();
  private entry(url: string) {
    if (!url) return undefined;
    let entry = this.entries.get(url);
    if (!entry) {
      const image = this.createImage();
      entry = { image, ready: false, listeners: new Set() };
      this.entries.set(url, entry);
      const resource = entry;
      image.onload = () => {
        resource.ready = true;
        resource.listeners.forEach((listener) => listener());
      };
      image.src = url;
    }
    return entry;
  }
  get(url: string) {
    const entry = this.entry(url);
    return entry?.ready ? entry.image : undefined;
  }
  subscribe(url: string, listener: () => void) {
    const entry = this.entry(url);
    entry?.listeners.add(listener);
    return () => {
      entry?.listeners.delete(listener);
    };
  }
}
