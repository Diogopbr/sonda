import type { CheckState } from './types';

type StorageAdapter = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
function browserStorage(): StorageAdapter | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export class CheckKeys {
  private readonly memory = new Map<string, string>();
  constructor(
    private readonly storage: StorageAdapter | null = browserStorage(),
    private readonly makeKey: () => string = () => crypto.randomUUID(),
  ) {}

  private address(workspace: string, monitor: string): string {
    return `sonda.check:${workspace}:${monitor}`;
  }

  getOrCreate(workspace: string, monitor: string): string {
    const address = this.address(workspace, monitor);
    let key = this.memory.get(address);
    if (!key) {
      try {
        key = this.storage?.getItem(address) ?? undefined;
      } catch {
        /* Keep an in-memory retry key. */
      }
      if (!key || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(key)) key = this.makeKey();
      this.memory.set(address, key);
      try {
        this.storage?.setItem(address, key);
      } catch {
        /* Storage is optional. */
      }
    }
    return key;
  }

  observe(workspace: string, monitor: string, state: CheckState): void {
    if (state === 'pending') return;
    const address = this.address(workspace, monitor);
    this.memory.delete(address);
    try {
      this.storage?.removeItem(address);
    } catch {
      /* Memory was already cleared. */
    }
  }
}
