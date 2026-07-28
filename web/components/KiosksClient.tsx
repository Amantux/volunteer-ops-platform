'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useId, useState } from 'react';
import { ApiError, getMe, getToken, type Me } from '@/lib/auth';
import {
  createKiosk,
  createKioskTask,
  listKioskTasks,
  listKiosks,
  patchKiosk,
  PANEL_TYPES,
  type Kiosk,
  type KioskMode,
  type KioskTask,
  type PanelConfig,
  type PanelType,
} from '@/lib/kiosk';

// Permissions this surface is gated on (mirror the backend contract).
const P_VIEW = 'kiosk.view';
const P_MANAGE = 'kiosk.manage';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; me: Me; kiosks: Kiosk[] }
  | { kind: 'no-access'; me: Me }
  | { kind: 'error'; message: string };

const MODE_OPTIONS: { value: KioskMode; label: string }[] = [
  { value: 'display', label: 'Display only (read-only signage)' },
  { value: 'shared', label: 'Shared (tap to check in / tick tasks)' },
];

const PANEL_LABELS: Record<PanelType, string> = {
  schedule: 'Schedule',
  checkin: 'Check-in',
  tasks: 'Tasks',
  fyi: 'FYI notice',
  roster: 'Roster',
  camera: 'Camera',
};

function errText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

function modeLabel(mode: KioskMode): string {
  return mode === 'shared' ? 'Shared' : 'Display only';
}

export default function KiosksClient() {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [notice, setNotice] = useState('');
  const [actionError, setActionError] = useState('');

  const bounceOn401 = useCallback(
    (err: unknown): boolean => {
      if (err instanceof ApiError && err.status === 401) {
        router.replace('/login');
        return true;
      }
      return false;
    },
    [router],
  );

  const load = useCallback(() => {
    if (!getToken()) {
      router.replace('/login');
      return;
    }
    setState({ kind: 'loading' });
    getMe()
      .then(async (me) => {
        if (!me.permissions.includes(P_VIEW)) {
          setState({ kind: 'no-access', me });
          return;
        }
        const kiosks = await listKiosks();
        setState({ kind: 'ready', me, kiosks });
      })
      .catch((err: unknown) => {
        if (bounceOn401(err)) return;
        setState({
          kind: 'error',
          message: errText(
            err,
            'We couldn’t load kiosks. Please refresh in a moment.',
          ),
        });
      });
  }, [router, bounceOn401]);

  useEffect(() => {
    load();
  }, [load]);

  const refresh = useCallback(async () => {
    try {
      const kiosks = await listKiosks();
      setState((prev) => (prev.kind === 'ready' ? { ...prev, kiosks } : prev));
    } catch (err) {
      if (bounceOn401(err)) return;
      setActionError(errText(err, 'We couldn’t refresh kiosks.'));
    }
  }, [bounceOn401]);

  if (state.kind === 'loading') {
    return (
      <div className="container page">
        <p role="status">Loading kiosks…</p>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className="container page">
        <h1>Kiosks</h1>
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t load kiosks</strong>
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
            <h1>Kiosks</h1>
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
            Viewing kiosks needs the “kiosk.view” permission, which your account
            doesn’t have. Ask an administrator to grant it.
          </p>
        </div>
      </div>
    );
  }

  const { me, kiosks } = state;
  const canManage = me.permissions.includes(P_MANAGE);

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1>Kiosks</h1>
          <p className="muted">
            Tablet displays for the front desk — today’s roster, self check-in,
            day-of tasks and notices. Open a kiosk’s display URL on the tablet.
          </p>
        </div>
        <Link className="btn btn-secondary" href="/dashboard">
          Back to dashboard
        </Link>
      </div>

      <div aria-live="polite">
        {notice && (
          <div className="alert alert-success" role="status">
            <p>{notice}</p>
          </div>
        )}
      </div>
      <div aria-live="assertive">
        {actionError && (
          <div className="alert alert-danger" role="alert">
            <strong>That didn’t work</strong>
            <p>{actionError}</p>
          </div>
        )}
      </div>

      <section className="section-gap" aria-labelledby="kiosks-heading">
        <h2 id="kiosks-heading">Your kiosks</h2>
        {kiosks.length === 0 ? (
          <div className="empty">
            <div className="empty-icon" aria-hidden="true">
              🖥️
            </div>
            <h3>No kiosks yet</h3>
            <p>
              Create your first kiosk below, then open its display URL on the
              front-desk tablet.
            </p>
          </div>
        ) : (
          <div className="kiosk-list">
            {kiosks.map((k) => (
              <KioskCard
                key={k.id}
                kiosk={k}
                canManage={canManage}
                onNotice={setNotice}
                onError={setActionError}
                onChanged={refresh}
                onAuthLost={() => router.replace('/login')}
              />
            ))}
          </div>
        )}
      </section>

      {canManage && (
        <CreateKioskForm
          onCreated={async () => {
            setNotice('Kiosk created.');
            await refresh();
          }}
          onAuthLost={() => router.replace('/login')}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// One kiosk: identity, display URL, active toggle, panel editor, task manager.
// ---------------------------------------------------------------------------
function KioskCard({
  kiosk,
  canManage,
  onNotice,
  onError,
  onChanged,
  onAuthLost,
}: {
  kiosk: Kiosk;
  canManage: boolean;
  onNotice: (msg: string) => void;
  onError: (msg: string) => void;
  onChanged: () => void | Promise<void>;
  onAuthLost: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [busyActive, setBusyActive] = useState(false);

  // The display URL is what you open on the tablet. Built from the current
  // origin so it works in any environment.
  const displayUrl =
    typeof window !== 'undefined'
      ? `${window.location.origin}/kiosk/${kiosk.token}`
      : `/kiosk/${kiosk.token}`;

  async function copyUrl() {
    try {
      await navigator.clipboard.writeText(displayUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      onError('Couldn’t copy — select and copy the URL manually.');
    }
  }

  async function toggleActive() {
    onError('');
    setBusyActive(true);
    try {
      await patchKiosk(kiosk.id, { is_active: !kiosk.is_active });
      onNotice(
        `Kiosk “${kiosk.name}” ${kiosk.is_active ? 'deactivated' : 'activated'}.`,
      );
      await onChanged();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      onError(errText(err, 'We couldn’t update that kiosk.'));
    } finally {
      setBusyActive(false);
    }
  }

  return (
    <article className="panel kiosk-card">
      <div className="kiosk-card-head">
        <div>
          <h3 className="kiosk-card-title">{kiosk.name}</h3>
          <div className="kiosk-meta">
            <span className="pill pill-neutral">{modeLabel(kiosk.mode)}</span>
            <span
              className={kiosk.is_active ? 'pill pill-open' : 'pill pill-danger'}
            >
              {kiosk.is_active ? 'Active' : 'Inactive'}
            </span>
            {kiosk.location && (
              <span className="muted">📍 {kiosk.location}</span>
            )}
          </div>
        </div>
        {canManage && (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={toggleActive}
            disabled={busyActive}
            aria-pressed={kiosk.is_active}
          >
            {busyActive
              ? 'Saving…'
              : kiosk.is_active
                ? 'Deactivate'
                : 'Activate'}
          </button>
        )}
      </div>

      <div className="field">
        <span className="kiosk-url-label">Display URL (open on the tablet)</span>
        <div className="kiosk-url-row">
          <code className="kiosk-url">{displayUrl}</code>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={copyUrl}
          >
            {copied ? 'Copied ✓' : 'Copy'}
          </button>
        </div>
      </div>

      {canManage && (
        <>
          <PanelEditor
            kiosk={kiosk}
            onNotice={onNotice}
            onError={onError}
            onChanged={onChanged}
            onAuthLost={onAuthLost}
          />
          <TaskManager
            kioskId={kiosk.id}
            onError={onError}
            onAuthLost={onAuthLost}
          />
        </>
      )}
    </article>
  );
}

// ---------------------------------------------------------------------------
// Panel editor — ordered list of panels; add / remove / reorder; fyi panels
// carry title + text. Save writes the whole ordered list back via PATCH panels.
// ---------------------------------------------------------------------------
function PanelEditor({
  kiosk,
  onNotice,
  onError,
  onChanged,
  onAuthLost,
}: {
  kiosk: Kiosk;
  onNotice: (msg: string) => void;
  onError: (msg: string) => void;
  onChanged: () => void | Promise<void>;
  onAuthLost: () => void;
}) {
  const addId = useId();
  const [panels, setPanels] = useState<PanelConfig[]>(kiosk.panels ?? []);
  const [addType, setAddType] = useState<PanelType>('schedule');
  const [busy, setBusy] = useState(false);

  // Keep local edits in sync when the parent reloads the kiosk list.
  useEffect(() => {
    setPanels(kiosk.panels ?? []);
  }, [kiosk.panels]);

  function addPanel() {
    setPanels((prev) => [
      ...prev,
      addType === 'fyi' ? { type: 'fyi', title: '', text: '' } : { type: addType },
    ]);
  }

  function removePanel(index: number) {
    setPanels((prev) => prev.filter((_, i) => i !== index));
  }

  function move(index: number, delta: number) {
    setPanels((prev) => {
      const next = [...prev];
      const target = index + delta;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function updateFyi(index: number, field: 'title' | 'text', value: string) {
    setPanels((prev) =>
      prev.map((p, i) => (i === index ? { ...p, [field]: value } : p)),
    );
  }

  async function save() {
    onError('');
    setBusy(true);
    try {
      await patchKiosk(kiosk.id, { panels });
      onNotice(`Panels saved for “${kiosk.name}”.`);
      await onChanged();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      onError(errText(err, 'We couldn’t save the panels.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="kiosk-sub" aria-labelledby={`panels-${kiosk.id}`}>
      <h4 id={`panels-${kiosk.id}`}>Panels</h4>
      {panels.length === 0 ? (
        <p className="muted">
          No panels yet. Add one below — panels show top-to-bottom on the tablet.
        </p>
      ) : (
        <ol className="kiosk-panel-list">
          {panels.map((p, i) => (
            <li key={i} className="kiosk-panel-row">
              <div className="kiosk-panel-main">
                <span className="pill pill-neutral">{PANEL_LABELS[p.type]}</span>
                {p.type === 'fyi' && (
                  <div className="kiosk-fyi-fields">
                    <label className="field">
                      <span>Title</span>
                      <input
                        type="text"
                        value={p.title ?? ''}
                        onChange={(e) => updateFyi(i, 'title', e.target.value)}
                        placeholder="e.g. Fire drill at 2pm"
                      />
                    </label>
                    <label className="field">
                      <span>Text</span>
                      <textarea
                        className="cms-textarea"
                        value={p.text ?? ''}
                        onChange={(e) => updateFyi(i, 'text', e.target.value)}
                        placeholder="Details shown under the headline"
                      />
                    </label>
                  </div>
                )}
              </div>
              <div className="kiosk-panel-actions">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => move(i, -1)}
                  disabled={i === 0}
                  aria-label={`Move ${PANEL_LABELS[p.type]} up`}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => move(i, 1)}
                  disabled={i === panels.length - 1}
                  aria-label={`Move ${PANEL_LABELS[p.type]} down`}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => removePanel(i)}
                  aria-label={`Remove ${PANEL_LABELS[p.type]} panel`}
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ol>
      )}

      <div className="cms-field-row kiosk-add-panel">
        <div className="field cms-grow">
          <label htmlFor={addId}>Add a panel</label>
          <select
            id={addId}
            className="cms-select"
            value={addType}
            onChange={(e) => setAddType(e.target.value as PanelType)}
          >
            {PANEL_TYPES.map((t) => (
              <option key={t} value={t}>
                {PANEL_LABELS[t]}
              </option>
            ))}
          </select>
        </div>
        <div className="kiosk-add-actions">
          <button type="button" className="btn btn-secondary" onClick={addPanel}>
            Add panel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={save}
            disabled={busy}
          >
            {busy ? 'Saving…' : 'Save panels'}
          </button>
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Day-of tasks manager — list existing tasks and add new ones by label.
// ---------------------------------------------------------------------------
function TaskManager({
  kioskId,
  onError,
  onAuthLost,
}: {
  kioskId: number;
  onError: (msg: string) => void;
  onAuthLost: () => void;
}) {
  const labelId = useId();
  const [tasks, setTasks] = useState<KioskTask[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [label, setLabel] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const t = await listKioskTasks(kioskId);
      setTasks([...t].sort((a, b) => a.sort_order - b.sort_order));
      setLoaded(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      onError(errText(err, 'We couldn’t load day-of tasks.'));
    }
  }, [kioskId, onError, onAuthLost]);

  useEffect(() => {
    load();
  }, [load]);

  async function addTask(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const value = label.trim();
    if (!value) {
      onError('Enter a task label.');
      return;
    }
    onError('');
    setBusy(true);
    try {
      await createKioskTask(kioskId, { label: value });
      setLabel('');
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      onError(errText(err, 'We couldn’t add that task.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="kiosk-sub" aria-labelledby={`tasks-${kioskId}`}>
      <h4 id={`tasks-${kioskId}`}>Day-of tasks</h4>
      {loaded && tasks.length === 0 ? (
        <p className="muted">No tasks yet. Add one below.</p>
      ) : (
        <ul className="kiosk-task-list">
          {tasks.map((t) => (
            <li key={t.id}>{t.label}</li>
          ))}
        </ul>
      )}
      <form className="kiosk-add-panel" onSubmit={addTask}>
        <div className="field cms-grow">
          <label htmlFor={labelId}>Task label</label>
          <input
            id={labelId}
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. Unlock the side door"
          />
        </div>
        <div className="kiosk-add-actions">
          <button type="submit" className="btn btn-secondary" disabled={busy}>
            {busy ? 'Adding…' : 'Add task'}
          </button>
        </div>
      </form>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Create a new kiosk.
// ---------------------------------------------------------------------------
function CreateKioskForm({
  onCreated,
  onAuthLost,
}: {
  onCreated: () => void | Promise<void>;
  onAuthLost: () => void;
}) {
  const nameId = useId();
  const modeId = useId();
  const locationId = useId();

  const [name, setName] = useState('');
  const [mode, setMode] = useState<KioskMode>('display');
  const [location, setLocation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    const trimmed = name.trim();
    if (!trimmed) {
      setError('A kiosk name is required.');
      return;
    }
    setBusy(true);
    try {
      await createKiosk({
        name: trimmed,
        mode,
        location: location.trim() || undefined,
      });
      setName('');
      setLocation('');
      setMode('display');
      await onCreated();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      setError(errText(err, 'We couldn’t create that kiosk. Try again.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel section-gap" aria-labelledby="create-kiosk-heading">
      <h2 id="create-kiosk-heading">Create a kiosk</h2>
      <form onSubmit={onSubmit} noValidate>
        <div className="cms-field-row">
          <div className="field cms-grow">
            <label htmlFor={nameId}>
              Name <span className="req">*</span>
            </label>
            <input
              id={nameId}
              type="text"
              placeholder="e.g. Front desk"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="field cms-grow">
            <label htmlFor={modeId}>Mode</label>
            <select
              id={modeId}
              className="cms-select"
              value={mode}
              onChange={(e) => setMode(e.target.value as KioskMode)}
            >
              {MODE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field cms-grow">
            <label htmlFor={locationId}>Location</label>
            <input
              id={locationId}
              type="text"
              placeholder="e.g. Main lobby"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            />
          </div>
        </div>
        <div aria-live="assertive">
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
        </div>
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? 'Creating…' : 'Create kiosk'}
        </button>
      </form>
    </section>
  );
}
