export class QueryGate {
  private sequence = 0;
  private key: string | null = null;
  private controller: AbortController | null = null;

  cancel(): void {
    this.sequence++;
    this.controller?.abort();
    this.key = null;
  }

  async run<T>(key: string, loader: (signal: AbortSignal) => Promise<T>): Promise<T | null> {
    this.controller?.abort();
    const controller = new AbortController();
    this.controller = controller;
    this.key = key;
    const sequence = ++this.sequence;
    try {
      const value = await loader(controller.signal);
      return sequence === this.sequence && this.key === key && !controller.signal.aborted
        ? value
        : null;
    } catch (error) {
      if (controller.signal.aborted || sequence !== this.sequence || this.key !== key) return null;
      throw error;
    }
  }
}
