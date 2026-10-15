import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { expect, it, vi } from 'vitest';
import type { Monitor } from '../lib/types';
import MonitorControls from './MonitorControls.svelte';

it('keeps an edited scenario when an incident refresh returns the same remote mode', async () => {
  const monitor: Monitor = {
    id: 'monitor',
    name: 'API de pedidos',
    target_kind: 'fixture',
    target_url: 'https://example.com/probe/fixture',
    fixture_mode: 'unavailable',
    enabled: true,
    observed_state: 'unavailable',
    version: 4,
    interval_seconds: 60,
    failure_streak: 2,
    success_streak: 0,
    last_check: null,
    active_incident: null,
  };
  const change = vi.fn().mockResolvedValue(undefined);
  const props = { monitor, onVerify: vi.fn(), onChange: change, onReload: vi.fn() };
  const { rerender } = render(MonitorControls, props);
  const select = screen.getByLabelText('Cenário do alvo fictício');
  await fireEvent.change(select, { target: { value: 'available' } });
  expect(select).toHaveValue('available');
  await rerender({ ...props, monitor: { ...monitor, version: 5 } });
  expect(select).toHaveValue('available');
  await fireEvent.click(screen.getByRole('button', { name: 'Aplicar cenário' }));
  await waitFor(() => expect(change).toHaveBeenCalledWith({ fixture_mode: 'available' }, 5));
});
