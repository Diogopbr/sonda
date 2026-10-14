import { describe, expect, it, vi } from 'vitest';
import { ApiClient, ApiError } from './api';

describe('write context', () => {
  it('invokes browser fetch with the global receiver rather than the API client instance', async () => {
    const fetcher = vi.fn<typeof fetch>(function (this: unknown) {
      if (this !== globalThis) throw new TypeError('Illegal invocation');
      return Promise.resolve(new Response('{"demo_enabled":true}', { status: 200 }));
    });
    await expect(new ApiClient(fetcher).read('/api/capabilities')).resolves.toEqual({
      demo_enabled: true,
    });
  });
  it('preserves HTTP status when a gateway returns a JSON null error body', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response('null', { status: 503 }));
    await expect(new ApiClient(fetcher).read('/api/monitors')).rejects.toMatchObject({
      status: 503,
      code: 'REQUEST_FAILED',
    });
  });
  it('captures the workspace before asynchronous CSRF retrieval and sends the captured generation', async () => {
    const fetcher = vi.fn<typeof fetch>();
    let resolveCsrf!: (response: Response) => void;
    fetcher.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveCsrf = resolve;
        }),
    );
    fetcher.mockResolvedValueOnce(new Response(JSON.stringify({ id: 'saved' }), { status: 200 }));
    const client = new ApiClient(fetcher);
    let workspace = 'generation-a';
    const promise = client.write(
      '/api/incidents/id/ack',
      { comment: 'Rascunho original', expected_version: 1 },
      workspace,
    );
    workspace = 'generation-b';
    resolveCsrf(
      new Response(JSON.stringify({ csrf: 'token-from-current-cookie' }), { status: 200 }),
    );
    await promise;
    const sent = new Headers(fetcher.mock.calls[1][1]?.headers);
    expect(sent.get('X-Sonda-Workspace')).toBe('generation-a');
    expect(sent.get('X-CSRF-Token')).toBe('token-from-current-cookie');
    expect(workspace).toBe('generation-b');
  });

  it.each([404, 409, 419, 429])(
    'keeps structured errors and Retry-After available for recovery (%s)',
    async (status) => {
      const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: 'VERSION_CONFLICT',
              message: 'Revise os dados.',
              current: { version: 2 },
            },
          }),
          { status, headers: { 'Retry-After': '23' } },
        ),
      );
      try {
        await new ApiClient(fetcher).read('/api/monitors/id', 'generation-a');
        expect.fail('request must fail');
      } catch (error) {
        expect(error).toBeInstanceOf(ApiError);
        expect(error).toMatchObject({
          status,
          code: 'VERSION_CONFLICT',
          retryAfter: 23,
          current: { version: 2 },
        });
      }
      expect(new Headers(fetcher.mock.calls[0][1]?.headers).get('X-Sonda-Workspace')).toBe(
        'generation-a',
      );
    },
  );
});
