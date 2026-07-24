'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import {
  ApiError,
  getInstance,
  getMe,
  getSubmission,
  getToken,
  listSubmissions,
  runTransition,
  type FormSubmission,
  type Me,
  type WorkflowInstance,
  type WorkflowTransition,
} from '@/lib/auth';

// Permission key (mirrors the backend contract).
const P_REVIEW = 'forms.review';

// This inbox is scoped to incident reports for v1.
const FORM_KEY = 'incident_report';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; me: Me; submissions: FormSubmission[] }
  | { kind: 'error'; message: string };

type Detail =
  | { kind: 'none' }
  | { kind: 'loading'; id: number }
  | {
      kind: 'ready';
      submission: FormSubmission;
      instance: WorkflowInstance | null;
    }
  | { kind: 'error'; id: number; message: string };

function errText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

// "start_review" → "Start review"; "return_to_submitter" → "Return to submitter".
function humanize(name: string): string {
  const spaced = name.replace(/[_-]+/g, ' ').trim();
  return spaced ? spaced[0].toUpperCase() + spaced.slice(1) : name;
}

// Render an answer value (which may be a scalar, flag, or list) as plain text.
function formatAnswer(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) return value.map((v) => String(v)).join(', ');
  return String(value);
}

export default function RequestsClient() {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [detail, setDetail] = useState<Detail>({ kind: 'none' });

  // Per-detail async feedback (transitions).
  const [actionError, setActionError] = useState('');
  const [actionNotice, setActionNotice] = useState('');
  const [busy, setBusy] = useState(false);

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
        // Without forms.review the list endpoint would 403; show the access
        // note instead of firing a request we know will fail.
        const submissions = me.permissions.includes(P_REVIEW)
          ? await listSubmissions(FORM_KEY)
          : [];
        setState({ kind: 'ready', me, submissions });
      })
      .catch((err: unknown) => {
        if (bounceOn401(err)) return;
        setState({
          kind: 'error',
          message: errText(
            err,
            'We couldn’t load the requests inbox. Please refresh in a moment.',
          ),
        });
      });
  }, [router, bounceOn401]);

  useEffect(() => {
    load();
  }, [load]);

  // Load (or reload) the selected submission plus its workflow instance.
  const loadDetail = useCallback(
    async (id: number) => {
      setActionError('');
      setActionNotice('');
      setDetail({ kind: 'loading', id });
      try {
        const submission = await getSubmission(id);
        const instance =
          submission.workflow_instance_id != null
            ? await getInstance(submission.workflow_instance_id)
            : null;
        setDetail({ kind: 'ready', submission, instance });
      } catch (err) {
        if (bounceOn401(err)) return;
        setDetail({
          kind: 'error',
          id,
          message: errText(err, 'We couldn’t load that submission.'),
        });
      }
    },
    [bounceOn401],
  );

  // Invoke a transition, then re-fetch so state + allowed actions stay honest.
  async function onTransition(
    instance: WorkflowInstance,
    transition: WorkflowTransition,
  ) {
    setActionError('');
    setActionNotice('');
    setBusy(true);
    try {
      // Stable per (instance, transition): a retry of the same intent dedupes.
      const key = `${instance.id}:${transition.name}`;
      await runTransition(instance.id, transition.name, '', key);
      if (transition.requires_approval) {
        setActionNotice(
          'Recorded — this action needs a second approver. It completes once another authorised reviewer confirms it.',
        );
      } else {
        setActionNotice(`Done: ${humanize(transition.name)}.`);
      }
      await loadDetailKeepNotice(instance.id);
    } catch (err) {
      if (bounceOn401(err)) return;
      setActionError(errText(err, 'That action didn’t work. Please try again.'));
    } finally {
      setBusy(false);
    }
  }

  // Re-fetch the detail without clearing the just-set notice.
  async function loadDetailKeepNotice(id: number) {
    try {
      const submission = await getSubmission(id);
      const instance =
        submission.workflow_instance_id != null
          ? await getInstance(submission.workflow_instance_id)
          : null;
      setDetail({ kind: 'ready', submission, instance });
    } catch (err) {
      if (bounceOn401(err)) return;
      setActionError(errText(err, 'We couldn’t refresh the submission.'));
    }
  }

  if (state.kind === 'loading') {
    return (
      <div className="container page">
        <p role="status">Loading the requests inbox…</p>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className="container page">
        <h1>Requests</h1>
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t load the requests inbox</strong>
          <p>{state.message}</p>
        </div>
      </div>
    );
  }

  const { me, submissions } = state;

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1>Requests</h1>
          <p className="muted">
            Review incident reports and move them through their workflow.
          </p>
        </div>
        <Link className="btn btn-secondary" href="/dashboard">
          Back to dashboard
        </Link>
      </div>

      {!me.permissions.includes(P_REVIEW) ? (
        <div className="alert alert-warning" role="note">
          <strong>You don’t have access to reviews</strong>
          <p>
            Reviewing incident reports needs the “forms.review” permission. Ask
            an administrator if you think you should have it.
          </p>
        </div>
      ) : (
        <div className="detail-grid">
          <div>
            <h2>Incident reports</h2>
            {submissions.length === 0 ? (
              <div className="empty">
                <div className="empty-icon" aria-hidden="true">
                  📋
                </div>
                <h2>Nothing to review</h2>
                <p>There are no incident reports in the queue right now.</p>
              </div>
            ) : (
              <ul className="card-list stack">
                {submissions.map((s) => {
                  const active =
                    (detail.kind === 'ready' &&
                      detail.submission.id === s.id) ||
                    (detail.kind === 'loading' && detail.id === s.id);
                  return (
                    <li className="card" key={s.id}>
                      <button
                        type="button"
                        className="card-link"
                        style={{
                          cursor: 'pointer',
                          width: '100%',
                          textAlign: 'left',
                          background: 'none',
                          border: 'none',
                          font: 'inherit',
                        }}
                        aria-pressed={active}
                        onClick={() => void loadDetail(s.id)}
                      >
                        <div className="row-head">
                          <strong>Report #{s.id}</strong>
                          <span className="pill pill-draft">{s.status}</span>
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className="panel">
            <DetailPane
              detail={detail}
              busy={busy}
              actionError={actionError}
              actionNotice={actionNotice}
              onTransition={onTransition}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function DetailPane({
  detail,
  busy,
  actionError,
  actionNotice,
  onTransition,
}: {
  detail: Detail;
  busy: boolean;
  actionError: string;
  actionNotice: string;
  onTransition: (
    instance: WorkflowInstance,
    transition: WorkflowTransition,
  ) => void;
}) {
  if (detail.kind === 'none') {
    return (
      <p className="muted">
        Select a report on the left to see its details and the actions available
        to you.
      </p>
    );
  }
  if (detail.kind === 'loading') {
    return <p role="status">Loading submission…</p>;
  }
  if (detail.kind === 'error') {
    return (
      <div className="alert alert-danger" role="alert">
        <strong>We couldn’t load that submission</strong>
        <p>{detail.message}</p>
      </div>
    );
  }

  const { submission, instance } = detail;
  const answerKeys = Object.keys(submission.answers);

  return (
    <div>
      <div className="row-head">
        <h2 style={{ margin: 0 }}>Report #{submission.id}</h2>
        <span className="pill pill-draft">{submission.status}</span>
      </div>

      <h3 className="section-gap">Answers</h3>
      {answerKeys.length === 0 ? (
        <p className="muted">No answers were recorded.</p>
      ) : (
        <dl className="detail-grid-inline">
          {answerKeys.map((key) => (
            <div key={key}>
              <dt>{humanizeKey(key)}</dt>
              <dd>{formatAnswer(submission.answers[key])}</dd>
            </div>
          ))}
        </dl>
      )}

      <h3 className="section-gap">Workflow</h3>
      {!instance ? (
        <p className="muted">This submission has no workflow instance.</p>
      ) : (
        <>
          <dl className="detail-grid-inline">
            <div>
              <dt>Current state</dt>
              <dd>
                <span className="pill pill-open">
                  {humanizeKey(instance.current_state)}
                </span>
              </dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{instance.status}</dd>
            </div>
            <div>
              <dt>Deadline</dt>
              <dd>
                {instance.deadline_at ? (
                  <time dateTime={instance.deadline_at}>
                    {new Date(instance.deadline_at).toLocaleString('en-GB')}
                  </time>
                ) : (
                  'No deadline'
                )}
              </dd>
            </div>
          </dl>

          {actionNotice && (
            <div className="alert alert-success" role="status" aria-live="polite">
              <p>{actionNotice}</p>
            </div>
          )}
          {actionError && (
            <div className="alert alert-danger" role="alert" aria-live="assertive">
              <strong>That didn’t work</strong>
              <p>{actionError}</p>
            </div>
          )}

          {instance.allowed_transitions.length === 0 ? (
            <p className="muted">No actions are available to you right now.</p>
          ) : (
            <div className="social-actions">
              {instance.allowed_transitions.map((t) => (
                <button
                  key={t.name}
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={busy}
                  onClick={() => onTransition(instance, t)}
                >
                  {humanize(t.name)}
                  {t.requires_approval ? ' (needs approval)' : ''}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// Answer / state keys arrive as snake_case machine keys; make them readable.
function humanizeKey(key: string): string {
  const spaced = key.replace(/[_-]+/g, ' ').trim();
  return spaced ? spaced[0].toUpperCase() + spaced.slice(1) : key;
}
