import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { expect, it, vi } from 'vitest';
import { ApiError } from '../lib/api';
import type { IncidentSummary } from '../lib/types';
import AcknowledgementForm from './AcknowledgementForm.svelte';

const incident: IncidentSummary = {
  id: 'incident',
  monitor_id: 'monitor',
  state: 'open',
  version: 1,
  first_failure_at: '2026-10-14T12:00:00Z',
  confirmed_at: '2026-10-14T12:01:00Z',
  first_failure_check_id: 'first',
  confirmation_check_id: 'second',
  resolved_at: null,
  resolution_check_id: null,
  acknowledged_at: null,
  acknowledged_by: null,
  acknowledgement: null,
};

it.each([404, 409, 0])(
  'preserves the comment after ownership, version or network failure (%s)',
  async (status) => {
    const send = vi
      .fn()
      .mockRejectedValue(
        status
          ? new ApiError(
              status,
              status === 404 ? 'NOT_FOUND' : 'VERSION_CONFLICT',
              'Revise o registro.',
            )
          : new TypeError('network'),
      );
    render(AcknowledgementForm, { incident, onAcknowledge: send, onReload: vi.fn() });
    const input = screen.getByLabelText('Comentário de investigação');
    await fireEvent.input(input, { target: { value: 'Revisando o proxy.\nConferindo a origem.' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Reconhecer incidente' }));
    await waitFor(() =>
      expect(send).toHaveBeenCalledWith('Revisando o proxy.\nConferindo a origem.', 1),
    );
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(input).toHaveValue('Revisando o proxy.\nConferindo a origem.');
    expect(screen.getByRole('alert')).toHaveFocus();
  },
);

it('requires an explicit refresh after conflict and keeps the unsent draft when another actor already acknowledged', async () => {
  const send = vi
    .fn()
    .mockRejectedValue(new ApiError(409, 'VERSION_CONFLICT', 'O incidente mudou.'));
  const reload = vi.fn().mockResolvedValue(undefined);
  const { rerender } = render(AcknowledgementForm, {
    incident,
    onAcknowledge: send,
    onReload: reload,
  });
  await fireEvent.input(screen.getByLabelText('Comentário de investigação'), {
    target: { value: 'Rascunho da outra aba.' },
  });
  await fireEvent.click(screen.getByRole('button', { name: 'Reconhecer incidente' }));
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Revisar dados atuais' })).toBeInTheDocument(),
  );
  expect(reload).not.toHaveBeenCalled();
  await fireEvent.click(screen.getByRole('button', { name: 'Revisar dados atuais' }));
  expect(reload).toHaveBeenCalledTimes(1);
  await rerender({
    incident: {
      ...incident,
      version: 2,
      state: 'acknowledged',
      acknowledgement: 'Comentário confirmado.',
      acknowledged_at: '2026-10-14T12:02:00Z',
      acknowledged_by: { id: 'actor', name: 'Visitante' },
    },
  });
  expect(screen.getByLabelText('Rascunho não enviado')).toHaveValue('Rascunho da outra aba.');
  expect(screen.queryByRole('button', { name: 'Reconhecer incidente' })).not.toBeInTheDocument();
});
