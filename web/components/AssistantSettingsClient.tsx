'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useId, useState } from 'react';
import {
  type AgentSettings,
  type AgentSettingsPatch,
  getAgentSettings,
  listAgentModels,
  putAgentSettings,
} from '@/lib/agent';
import { ApiError, getMe, getToken, type Me } from '@/lib/auth';

// The permission this surface is gated on (mirrors the backend contract).
const P_CONFIGURE = 'assistant.configure';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; me: Me; settings: AgentSettings }
  | { kind: 'no-access'; me: Me }
  | { kind: 'error'; message: string };

// Editable form mirror of AgentSettings. The API key is write-only: we never
// receive it, so the field starts blank and an empty value leaves it unchanged.
interface FormState {
  provider: string;
  base_url: string;
  model: string;
  api_key: string;
  system_prompt: string;
  timeout: string;
  max_steps: string;
}

function toForm(s: AgentSettings): FormState {
  return {
    provider: s.provider,
    base_url: s.base_url,
    model: s.model,
    api_key: '',
    system_prompt: s.system_prompt,
    timeout: String(s.timeout),
    max_steps: String(s.max_steps),
  };
}

export default function AssistantSettingsClient() {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [form, setForm] = useState<FormState>({
    provider: 'off',
    base_url: '',
    model: '',
    api_key: '',
    system_prompt: '',
    timeout: '60',
    max_steps: '6',
  });
  const [hasApiKey, setHasApiKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');
  const [models, setModels] = useState<string[]>([]);
  const [modelsMsg, setModelsMsg] = useState('');
  const [probing, setProbing] = useState(false);

  const providerId = useId();
  const baseUrlId = useId();
  const modelId = useId();
  const modelListId = useId();
  const apiKeyId = useId();
  const promptId = useId();
  const timeoutId = useId();
  const maxStepsId = useId();

  const load = useCallback(() => {
    if (!getToken()) {
      router.replace('/login');
      return;
    }
    setState({ kind: 'loading' });
    getMe()
      .then(async (me) => {
        if (!me.permissions.includes(P_CONFIGURE)) {
          setState({ kind: 'no-access', me });
          return;
        }
        const settings = await getAgentSettings();
        setForm(toForm(settings));
        setHasApiKey(settings.has_api_key);
        setState({ kind: 'ready', me, settings });
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 401) {
          router.replace('/login');
          return;
        }
        setState({
          kind: 'error',
          message:
            err instanceof ApiError
              ? err.message
              : 'We couldn’t load the assistant settings. Please refresh in a moment.',
        });
      });
  }, [router]);

  useEffect(() => {
    load();
  }, [load]);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaveMsg('');
    const patch: AgentSettingsPatch = {
      provider: form.provider,
      base_url: form.base_url,
      model: form.model,
      system_prompt: form.system_prompt,
      timeout: Number(form.timeout),
      max_steps: Number(form.max_steps),
    };
    // Only send the key when the admin typed a new one; blank keeps the existing.
    if (form.api_key.trim()) patch.api_key = form.api_key.trim();
    try {
      const settings = await putAgentSettings(patch);
      setForm(toForm(settings));
      setHasApiKey(settings.has_api_key);
      setState((s) =>
        s.kind === 'ready' ? { ...s, settings } : s,
      );
      setSaveMsg('Saved — the assistant will use these settings.');
    } catch (err) {
      setSaveMsg(
        err instanceof ApiError
          ? `Couldn’t save: ${err.message}`
          : 'Couldn’t save. Please try again.',
      );
    } finally {
      setSaving(false);
    }
  }

  async function onListModels() {
    setProbing(true);
    setModelsMsg('');
    try {
      const { models: found } = await listAgentModels();
      setModels(found);
      setModelsMsg(
        found.length
          ? `Found ${found.length} model${found.length === 1 ? '' : 's'}.`
          : 'No models returned by the provider.',
      );
    } catch (err) {
      setModelsMsg(
        err instanceof ApiError
          ? `Couldn’t list models: ${err.message}`
          : 'Couldn’t reach the provider to list models.',
      );
    } finally {
      setProbing(false);
    }
  }

  if (state.kind === 'loading') {
    return (
      <div className="container page">
        <p role="status">Loading assistant settings…</p>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className="container page">
        <h1>AI Assistant</h1>
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t load the settings</strong>
          <p>{state.message}</p>
        </div>
      </div>
    );
  }

  if (state.kind === 'no-access') {
    return (
      <div className="container page">
        <div className="page-head">
          <div>
            <h1>AI Assistant</h1>
          </div>
          <Link className="btn btn-secondary" href="/dashboard">
            Back to dashboard
          </Link>
        </div>
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">
            🔒
          </div>
          <h2>Insufficient access</h2>
          <p>
            Configuring the assistant needs the “assistant.configure”
            permission, which your account doesn’t have. Ask an organisation
            admin to grant it.
          </p>
        </div>
      </div>
    );
  }

  const showConnection = form.provider !== 'off';

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1>AI Assistant</h1>
          <p className="muted">
            Connect a language model to power the chat assistant. The API key is
            stored securely and never shown here.
          </p>
        </div>
        <Link className="btn btn-secondary" href="/dashboard">
          Back to dashboard
        </Link>
      </div>

      <form className="panel" onSubmit={onSave} style={{ maxWidth: 560 }}>
        <div className="field">
          <label htmlFor={providerId}>Provider</label>
          <select
            id={providerId}
            className="cms-select"
            value={form.provider}
            onChange={(e) => update('provider', e.target.value)}
          >
            <option value="off">Off (disabled)</option>
            <option value="ollama">Ollama (local / cloud)</option>
            <option value="openai">OpenAI-compatible (OpenAI, OpenRouter, LiteLLM…)</option>
            <option value="anthropic">Anthropic</option>
          </select>
        </div>

        {showConnection && (
          <>
            <div className="field">
              <label htmlFor={baseUrlId}>Base URL</label>
              <p className="hint" id={`${baseUrlId}-hint`}>
                For Ollama, e.g. http://localhost:11434. Leave blank to use the
                provider default.
              </p>
              <input
                id={baseUrlId}
                type="url"
                value={form.base_url}
                aria-describedby={`${baseUrlId}-hint`}
                onChange={(e) => update('base_url', e.target.value)}
                placeholder="http://localhost:11434"
              />
            </div>

            <div className="field">
              <label htmlFor={modelId}>Model</label>
              <div className="cms-field-row">
                <input
                  id={modelId}
                  className="cms-grow"
                  list={modelListId}
                  value={form.model}
                  onChange={(e) => update('model', e.target.value)}
                  placeholder="e.g. llama3.1 or claude-3-5-sonnet"
                />
                <datalist id={modelListId}>
                  {models.map((m) => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => void onListModels()}
                  disabled={probing}
                >
                  {probing ? 'Listing…' : 'List models'}
                </button>
              </div>
              <p className="hint" role="status" aria-live="polite">
                {modelsMsg}
              </p>
            </div>

            <div className="field">
              <label htmlFor={apiKeyId}>API key</label>
              <p className="hint" id={`${apiKeyId}-hint`}>
                {hasApiKey
                  ? 'A key is set. Leave blank to keep it; type a new key to replace it.'
                  : 'Required for Anthropic. Optional for a local Ollama.'}
              </p>
              <input
                id={apiKeyId}
                type="password"
                autoComplete="off"
                value={form.api_key}
                aria-describedby={`${apiKeyId}-hint`}
                onChange={(e) => update('api_key', e.target.value)}
                placeholder={hasApiKey ? '•••••••••• (key set)' : 'sk-…'}
              />
            </div>

            <div className="field">
              <label htmlFor={promptId}>System prompt</label>
              <textarea
                id={promptId}
                className="cms-textarea"
                value={form.system_prompt}
                onChange={(e) => update('system_prompt', e.target.value)}
                placeholder="Instructions that shape the assistant’s tone and scope."
              />
            </div>

            <div className="cms-field-row">
              <div className="field cms-grow">
                <label htmlFor={timeoutId}>Timeout (seconds)</label>
                <input
                  id={timeoutId}
                  type="number"
                  min={1}
                  value={form.timeout}
                  onChange={(e) => update('timeout', e.target.value)}
                />
              </div>
              <div className="field cms-grow">
                <label htmlFor={maxStepsId}>Max steps</label>
                <input
                  id={maxStepsId}
                  type="number"
                  min={1}
                  value={form.max_steps}
                  onChange={(e) => update('max_steps', e.target.value)}
                />
              </div>
            </div>
          </>
        )}

        <div className="social-actions">
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Saving…' : 'Save settings'}
          </button>
          {showConnection && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void onListModels()}
              disabled={probing}
            >
              {probing ? 'Testing…' : 'Test / list models'}
            </button>
          )}
        </div>
        <p className="follow-up" role="status" aria-live="polite">
          {saveMsg}
        </p>
      </form>
    </div>
  );
}
