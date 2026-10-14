import { expect, it } from 'vitest';
import { CheckKeys } from './check-keys';

it('retains the accepted command key through network failure and reload until an actual final result', () => {
  const storage = new Map<string, string>();
  const adapter = {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => {
      storage.set(key, value);
    },
    removeItem: (key: string) => {
      storage.delete(key);
    },
  };
  const first = new CheckKeys(adapter, () => '00000000-0000-0000-0000-000000000001');
  const key = first.getOrCreate('a', 'monitor');
  first.observe('a', 'monitor', 'pending');
  const restarted = new CheckKeys(adapter, () => '00000000-0000-0000-0000-000000000002');
  expect(restarted.getOrCreate('a', 'monitor')).toBe(key);
  expect(restarted.getOrCreate('b', 'monitor')).not.toBe(key);
  restarted.observe('a', 'monitor', 'finished');
  expect(restarted.getOrCreate('a', 'monitor')).not.toBe(key);
});

it('continues to preserve keys if browser storage is unavailable', () => {
  const adapter = {
    getItem: () => {
      throw new Error('blocked');
    },
    setItem: () => {
      throw new Error('blocked');
    },
    removeItem: () => {
      throw new Error('blocked');
    },
  };
  const keys = new CheckKeys(adapter);
  expect(keys.getOrCreate('a', 'monitor')).toBe(keys.getOrCreate('a', 'monitor'));
});
