import { expect, it } from 'vitest';
import { QueryGate } from './query';

it('discards an older response after navigation to another monitor or generation', async () => {
  const gate = new QueryGate();
  let oldResolve!: (value: string) => void;
  let oldSignal!: AbortSignal;
  const old = gate.run('a:monitor-one', (signal) => {
    oldSignal = signal;
    return new Promise((resolve) => {
      oldResolve = resolve;
    });
  });
  expect(await gate.run('b:monitor-two', async () => 'current')).toBe('current');
  expect(oldSignal.aborted).toBe(true);
  oldResolve('obsolete');
  expect(await old).toBeNull();
});

it('discards an in-flight response when its view is destroyed', async () => {
  const gate = new QueryGate();
  let resolve!: (value: string) => void;
  const pending = gate.run(
    'scope:monitor',
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  gate.cancel();
  resolve('obsolete');
  expect(await pending).toBeNull();
});
