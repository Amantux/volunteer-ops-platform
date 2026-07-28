'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '@/lib/api';
import {
  getKioskDisplay,
  kioskCheckin,
  kioskToggleTask,
  type DisplaySignup,
  type DisplayTask,
  type KioskDisplayPayload,
  type ResolvedPanel,
} from '@/lib/kiosk';

const POLL_MS = 15_000;

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; data: KioskDisplayPayload; updatedAt: Date }
  | { kind: 'gone' } // 404 — bad or inactive token
  | { kind: 'error'; message: string };

function formatTime(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

function formatClock(d: Date): string {
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

export default function KioskDisplay({ token }: { token: string }) {
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [actionError, setActionError] = useState('');
  // Track the latest state kind so the poller can avoid clobbering a 404 screen.
  const stateKindRef = useRef<State['kind']>('loading');
  stateKindRef.current = state.kind;

  const load = useCallback(async () => {
    try {
      const data = await getKioskDisplay(token);
      setState({ kind: 'ready', data, updatedAt: new Date() });
      setActionError('');
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setState({ kind: 'gone' });
        return;
      }
      // On a transient error while already showing content, keep the last good
      // frame on screen rather than blanking the tablet — only surface a full
      // error screen if we never loaded anything.
      if (stateKindRef.current === 'ready') {
        setActionError('Couldn’t refresh — showing the last update.');
        return;
      }
      setState({
        kind: 'error',
        message:
          err instanceof ApiError
            ? err.message
            : 'We couldn’t reach the server. Retrying…',
      });
    }
  }, [token]);

  // Initial load + poll every ~15s to stay fresh. Stop polling once the token
  // is known-bad (404) so we don't hammer the server.
  useEffect(() => {
    load();
    const id = window.setInterval(() => {
      if (stateKindRef.current !== 'gone') load();
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  if (state.kind === 'loading') {
    return (
      <div className="kiosk-screen kiosk-center">
        <p className="kiosk-status" role="status">
          Loading…
        </p>
      </div>
    );
  }

  if (state.kind === 'gone') {
    return (
      <div className="kiosk-screen kiosk-center">
        <div className="kiosk-message">
          <div className="kiosk-message-icon" aria-hidden="true">
            🔌
          </div>
          <h1>This kiosk isn’t available</h1>
          <p>
            The link may be out of date or the kiosk has been switched off. Ask
            a coordinator for a current kiosk link.
          </p>
        </div>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className="kiosk-screen kiosk-center">
        <div className="kiosk-message">
          <div className="kiosk-message-icon" aria-hidden="true">
            📶
          </div>
          <h1>Can’t reach the server</h1>
          <p>{state.message}</p>
          <button type="button" className="kiosk-btn" onClick={() => load()}>
            Try again
          </button>
        </div>
      </div>
    );
  }

  const { data, updatedAt } = state;
  const shared = data.mode === 'shared';

  async function onCheckin(signupId: number) {
    setActionError('');
    try {
      await kioskCheckin(token, signupId);
      await load();
    } catch (err) {
      setActionError(
        err instanceof ApiError
          ? err.message
          : 'Check-in didn’t go through. Try again.',
      );
    }
  }

  async function onToggleTask(taskId: number) {
    setActionError('');
    try {
      await kioskToggleTask(token, taskId);
      await load();
    } catch (err) {
      setActionError(
        err instanceof ApiError
          ? err.message
          : 'That didn’t save. Try again.',
      );
    }
  }

  return (
    <div className="kiosk-screen">
      <header className="kiosk-topbar">
        <h1 className="kiosk-heading">{data.name}</h1>
        <div className="kiosk-topbar-meta">
          <span className="kiosk-updated" aria-live="polite">
            Updated {formatClock(updatedAt)}
          </span>
          <button
            type="button"
            className="kiosk-btn kiosk-btn-quiet"
            onClick={() => load()}
          >
            Refresh
          </button>
        </div>
      </header>

      <div aria-live="assertive">
        {actionError && (
          <div className="kiosk-banner" role="alert">
            {actionError}
          </div>
        )}
      </div>

      <div className="kiosk-panels">
        {data.panels.map((panel, i) => (
          <Panel
            key={i}
            panel={panel}
            shared={shared}
            onCheckin={onCheckin}
            onToggleTask={onToggleTask}
          />
        ))}
      </div>
    </div>
  );
}

function Panel({
  panel,
  shared,
  onCheckin,
  onToggleTask,
}: {
  panel: ResolvedPanel;
  shared: boolean;
  onCheckin: (signupId: number) => void;
  onToggleTask: (taskId: number) => void;
}) {
  switch (panel.type) {
    case 'fyi':
      return (
        <section className="kiosk-card kiosk-fyi">
          <h2 className="kiosk-fyi-title">{panel.title}</h2>
          {panel.text && <p className="kiosk-fyi-text">{panel.text}</p>}
        </section>
      );

    case 'schedule':
      return (
        <section className="kiosk-card" aria-label="Today’s schedule">
          <h2>Today</h2>
          <RosterRows signups={panel.signups} />
        </section>
      );

    case 'roster':
      return (
        <section className="kiosk-card" aria-label="Checked in">
          <h2>Here now</h2>
          <RosterRows signups={panel.signups.filter((s) => s.checked_in)} />
        </section>
      );

    case 'checkin':
      return (
        <section className="kiosk-card" aria-label="Check in">
          <h2>Check in</h2>
          <CheckinRows
            signups={panel.signups}
            shared={shared}
            onCheckin={onCheckin}
          />
        </section>
      );

    case 'tasks':
      return (
        <section className="kiosk-card" aria-label="Tasks">
          <h2>Tasks</h2>
          <TaskRows
            tasks={panel.tasks}
            shared={shared}
            onToggle={onToggleTask}
          />
        </section>
      );

    case 'camera':
      return (
        <section className="kiosk-card kiosk-camera">
          <div className="kiosk-camera-icon" aria-hidden="true">
            📷
          </div>
          <h2>Camera feeds coming soon</h2>
          {panel.note && <p className="kiosk-fyi-text">{panel.note}</p>}
        </section>
      );

    default:
      return null;
  }
}

function RosterRows({ signups }: { signups: DisplaySignup[] }) {
  if (signups.length === 0) {
    return <p className="kiosk-empty">No one scheduled yet.</p>;
  }
  return (
    <ul className="kiosk-roster">
      {signups.map((s) => (
        <li key={s.signup_id} className="kiosk-roster-row">
          <span className="kiosk-roster-name">{s.name}</span>
          <span className="kiosk-roster-role">{s.role}</span>
          {s.starts_at && (
            <span className="kiosk-roster-time">{formatTime(s.starts_at)}</span>
          )}
          {s.checked_in && (
            <span className="kiosk-checked" aria-label="Checked in">
              ✓
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

function CheckinRows({
  signups,
  shared,
  onCheckin,
}: {
  signups: DisplaySignup[];
  shared: boolean;
  onCheckin: (signupId: number) => void;
}) {
  if (signups.length === 0) {
    return <p className="kiosk-empty">No one scheduled yet.</p>;
  }
  return (
    <ul className="kiosk-checkin-list">
      {signups.map((s) => {
        if (s.checked_in) {
          return (
            <li key={s.signup_id} className="kiosk-checkin-done">
              <span className="kiosk-roster-name">{s.name}</span>
              <span className="kiosk-roster-role">{s.role}</span>
              <span className="kiosk-checked" aria-label="Checked in">
                ✓ Checked in
              </span>
            </li>
          );
        }
        // Not checked in. In shared mode this is a big tappable button; in
        // display-only mode it stays a read-only "expected" row.
        if (!shared) {
          return (
            <li key={s.signup_id} className="kiosk-checkin-pending">
              <span className="kiosk-roster-name">{s.name}</span>
              <span className="kiosk-roster-role">{s.role}</span>
              <span className="kiosk-roster-status">Expected</span>
            </li>
          );
        }
        return (
          <li key={s.signup_id}>
            <button
              type="button"
              className="kiosk-tap"
              onClick={() => onCheckin(s.signup_id)}
            >
              <span className="kiosk-roster-name">{s.name}</span>
              <span className="kiosk-roster-role">{s.role}</span>
              <span className="kiosk-tap-cue">Tap to check in</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function TaskRows({
  tasks,
  shared,
  onToggle,
}: {
  tasks: DisplayTask[];
  shared: boolean;
  onToggle: (taskId: number) => void;
}) {
  if (tasks.length === 0) {
    return <p className="kiosk-empty">No tasks for today.</p>;
  }
  return (
    <ul className="kiosk-task-checklist">
      {tasks.map((t) => {
        const box = t.done ? '☑' : '☐';
        if (!shared) {
          return (
            <li
              key={t.id}
              className={t.done ? 'kiosk-task-item done' : 'kiosk-task-item'}
            >
              <span className="kiosk-task-box" aria-hidden="true">
                {box}
              </span>
              <span>{t.label}</span>
            </li>
          );
        }
        return (
          <li key={t.id}>
            <button
              type="button"
              className={t.done ? 'kiosk-tap kiosk-tap-done' : 'kiosk-tap'}
              onClick={() => onToggle(t.id)}
              aria-pressed={t.done}
            >
              <span className="kiosk-task-box" aria-hidden="true">
                {box}
              </span>
              <span>{t.label}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
