export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly current: unknown = null,
    readonly retryAfter: number | null = null,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export class ApiClient {
  constructor(private readonly fetcher: typeof fetch = fetch) {}

  private async request<T>(path: string, init: RequestInit, workspace?: string): Promise<T> {
    const headers = new Headers(init.headers);
    if (workspace) headers.set('X-Sonda-Workspace', workspace);
    const response = await this.fetcher.call(globalThis, path, {
      ...init,
      headers,
      credentials: 'same-origin',
      cache: 'no-store',
    });
    let data: unknown;
    try {
      data = await response.json();
    } catch {
      throw new ApiError(
        response.status,
        'RESPONSE_INVALID',
        'A resposta não pôde ser lida. Tente novamente.',
      );
    }
    if (!response.ok) {
      const envelope = (typeof data === 'object' && data !== null ? data : {}) as {
        error?: { code?: string; message?: string; current?: unknown };
      };
      const delay = Number(response.headers.get('Retry-After'));
      throw new ApiError(
        response.status,
        envelope.error?.code ?? 'REQUEST_FAILED',
        envelope.error?.message ?? 'Não foi possível concluir a operação. Tente novamente.',
        envelope.error?.current ?? null,
        Number.isFinite(delay) && delay > 0 ? Math.ceil(delay) : null,
      );
    }
    return data as T;
  }

  read<T>(path: string, workspace?: string, signal?: AbortSignal): Promise<T> {
    return this.request(path, { method: 'GET', signal }, workspace);
  }

  async write<T>(path: string, value: unknown, workspace?: string, method = 'POST'): Promise<T> {
    const capturedWorkspace = workspace;
    const { csrf } = await this.read<{ csrf: string }>('/api/auth/csrf');
    return this.request(
      path,
      {
        method,
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify(value),
      },
      capturedWorkspace,
    );
  }
}

export const api = new ApiClient();

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return 'A conexão foi interrompida. Seu rascunho foi mantido; tente novamente.';
}
