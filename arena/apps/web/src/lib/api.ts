import { errorText, type ApiErrorBody, type AppErrorCode } from '@arena/shared';

export class ApiError extends Error {
  constructor(public readonly code: AppErrorCode, message: string, public readonly status: number) {
    super(message);
  }
}

let token: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setToken(value: string | null): void {
  token = value;
}

export function getToken(): string | null {
  return token;
}

export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler;
}

export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method: init.method ?? 'GET',
      headers: {
        ...(init.body !== undefined ? { 'content-type': 'application/json' } : {}),
        ...(token ? { authorization: `Bearer ${token}` } : {}),
      },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
    });
  } catch {
    throw new ApiError('NO_CONNECTION', errorText('NO_CONNECTION'), 0);
  }

  if (response.ok) return (await response.json()) as T;

  const body = (await response.json().catch(() => null)) as Partial<ApiErrorBody> | null;
  const code = body?.error ?? 'SERVER_ERROR';
  if (response.status === 401 && token) onUnauthorized?.();
  throw new ApiError(code, body?.message ?? errorText(code), response.status);
}
