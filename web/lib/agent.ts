// Client for the AI assistant surfaces (chat + admin settings).
// The chat endpoint streams Server-Sent Events; EventSource can't attach a
// bearer token or POST a body, so we consume the stream with fetch + a
// ReadableStream reader (see streamChat). Everything else reuses authFetch.

import { ApiError, apiBase, parseError } from '@/lib/api';
import { authFetch, clearToken, getToken } from '@/lib/auth';

// ---------------------------------------------------------------------------
// Types (mirror the backend contract)
// ---------------------------------------------------------------------------

// Drives whether the floating widget is active. `provider`/`model` are shown
// in the status pill; when disabled the input is locked with a hint.
export interface AgentConfig {
  enabled: boolean;
  provider: string;
  model: string | null;
}

export type ChatRole = 'user' | 'assistant';

// The wire shape resent to the stateless server each turn. The server caps the
// transcript length itself; we always send the full history we hold.
export interface ChatMessage {
  role: ChatRole;
  content: string;
}

// A tool the assistant ran mid-turn, rendered as an inline action card.
export interface AgentAction {
  kind: string;
  label: string;
}

// Terminal event of a streamed turn.
export interface AgentDone {
  provider: string;
  model: string;
}

// Admin settings. The API key is write-only: the server returns `has_api_key`
// (a boolean) and NEVER the key itself.
export interface AgentSettings {
  enabled: boolean;
  provider: string;
  base_url: string;
  model: string;
  system_prompt: string;
  timeout: number;
  max_steps: number;
  has_api_key: boolean;
}

// Partial update. Send `api_key` blank/omitted to keep the existing key.
export interface AgentSettingsPatch {
  provider?: string;
  base_url?: string;
  model?: string;
  api_key?: string;
  system_prompt?: string;
  timeout?: number;
  max_steps?: number;
}

// ---------------------------------------------------------------------------
// Config / settings (JSON over authFetch)
// ---------------------------------------------------------------------------

export async function getAgentConfig(): Promise<AgentConfig> {
  const res = await authFetch('/agent/config');
  return (await res.json()) as AgentConfig;
}

export async function getAgentSettings(): Promise<AgentSettings> {
  const res = await authFetch('/admin/agent-settings');
  return (await res.json()) as AgentSettings;
}

export async function putAgentSettings(
  patch: AgentSettingsPatch,
): Promise<AgentSettings> {
  const res = await authFetch('/admin/agent-settings', {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(patch),
  });
  return (await res.json()) as AgentSettings;
}

// Probe the provider (e.g. an Ollama tag list) for selectable models.
export async function listAgentModels(): Promise<{ models: string[] }> {
  const res = await authFetch('/admin/agent-settings/models', {
    method: 'POST',
  });
  return (await res.json()) as { models: string[] };
}

// ---------------------------------------------------------------------------
// Streaming chat (SSE over fetch + ReadableStream)
// ---------------------------------------------------------------------------

export interface StreamHandlers {
  onToken: (text: string) => void;
  onAction: (action: AgentAction) => void;
  onDone: (done: AgentDone) => void;
  signal?: AbortSignal;
}

// Parse one SSE event block (the text between two blank lines). An event may
// carry multiple `data:` lines per the SSE spec; we concatenate them.
function parseEventBlock(block: string): unknown | null {
  const dataLines: string[] = [];
  for (const line of block.split('\n')) {
    // SSE fields: keep everything after the first colon; a leading space is
    // stripped per spec. Lines without a colon (or comment lines) are ignored.
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''));
    }
  }
  if (dataLines.length === 0) return null;
  const payload = dataLines.join('\n').trim();
  if (!payload) return null;
  try {
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

// POST the transcript and stream the assistant's reply. Tokens arrive live via
// onToken; tool runs via onAction; the turn ends with onDone. Throws ApiError
// on a non-OK response (401 also clears the stored token).
export async function streamChat(
  messages: ChatMessage[],
  handlers: StreamHandlers,
): Promise<void> {
  const token = getToken();
  const headers = new Headers({
    'content-type': 'application/json',
    accept: 'text/event-stream',
  });
  if (token) headers.set('authorization', `Bearer ${token}`);

  const res = await fetch(`${apiBase()}/agent/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ messages }),
    cache: 'no-store',
    signal: handlers.signal,
  });

  if (res.status === 401) {
    clearToken();
    throw new ApiError(401, await parseError(res));
  }
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, await parseError(res));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const dispatch = (evt: unknown): void => {
    if (!evt || typeof evt !== 'object') return;
    const e = evt as Record<string, unknown>;
    if (e.type === 'token') {
      handlers.onToken(typeof e.text === 'string' ? e.text : '');
    } else if (e.type === 'action') {
      handlers.onAction({
        kind: typeof e.kind === 'string' ? e.kind : 'read',
        label: typeof e.label === 'string' ? e.label : '',
      });
    } else if (e.type === 'done') {
      handlers.onDone({
        provider: typeof e.provider === 'string' ? e.provider : '',
        model: typeof e.model === 'string' ? e.model : '',
      });
    }
  };

  // Read chunks, split on the SSE record separator (blank line), parse each.
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep = buffer.indexOf('\n\n');
    while (sep !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      dispatch(parseEventBlock(block));
      sep = buffer.indexOf('\n\n');
    }
  }
  // Flush any trailing event without a final blank-line terminator.
  if (buffer.trim()) dispatch(parseEventBlock(buffer));
}
