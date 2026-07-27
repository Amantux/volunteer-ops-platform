'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useId, useState } from 'react';
import {
  ApiError,
  createCampaign,
  getMe,
  getToken,
  listCampaigns,
  patchCampaign,
  type Campaign,
  type CampaignStatus,
  type Me,
} from '@/lib/auth';
import { formatMinor, parseDollarsToMinor } from '@/lib/money';

const P_VIEW = 'donation.view';
const P_MANAGE = 'donation.manage';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; me: Me; campaigns: Campaign[] }
  | { kind: 'no-access'; me: Me }
  | { kind: 'error'; message: string };

const STATUS_OPTIONS: { value: CampaignStatus; label: string }[] = [
  { value: 'draft', label: 'Draft' },
  { value: 'active', label: 'Active' },
  { value: 'paused', label: 'Paused' },
  { value: 'closed', label: 'Closed' },
  { value: 'archived', label: 'Archived' },
];

// Pill class per status — meaning carried by the label text, not colour alone.
const STATUS_PILL: Record<CampaignStatus, string> = {
  draft: 'pill pill-draft',
  active: 'pill pill-open',
  paused: 'pill pill-waitlist',
  closed: 'pill pill-neutral',
  archived: 'pill pill-neutral',
};

function statusLabel(status: CampaignStatus): string {
  return STATUS_OPTIONS.find((s) => s.value === status)?.label ?? status;
}

function errText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

export default function CampaignsClient() {
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
        const campaigns = await listCampaigns();
        setState({ kind: 'ready', me, campaigns });
      })
      .catch((err: unknown) => {
        if (bounceOn401(err)) return;
        setState({
          kind: 'error',
          message: errText(
            err,
            'We couldn’t load campaigns. Please refresh in a moment.',
          ),
        });
      });
  }, [router, bounceOn401]);

  useEffect(() => {
    load();
  }, [load]);

  const refresh = useCallback(async () => {
    try {
      const campaigns = await listCampaigns();
      setState((prev) =>
        prev.kind === 'ready' ? { ...prev, campaigns } : prev,
      );
    } catch (err) {
      if (bounceOn401(err)) return;
      setActionError(errText(err, 'We couldn’t refresh campaigns.'));
    }
  }, [bounceOn401]);

  if (state.kind === 'loading') {
    return (
      <div className="container page">
        <p role="status">Loading campaigns…</p>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className="container page">
        <h1>Campaigns</h1>
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t load campaigns</strong>
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
            <h1>Campaigns</h1>
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
            Viewing campaigns needs the “donation.view” permission, which your
            account doesn’t have. Ask an administrator to grant it.
          </p>
        </div>
      </div>
    );
  }

  const { me, campaigns } = state;
  const canManage = me.permissions.includes(P_MANAGE);

  async function onPatch(
    id: number,
    patch: Parameters<typeof patchCampaign>[1],
    successMsg: string,
  ) {
    setNotice('');
    setActionError('');
    try {
      await patchCampaign(id, patch);
      setNotice(successMsg);
      await refresh();
    } catch (err) {
      if (bounceOn401(err)) return;
      setActionError(
        errText(err, 'We couldn’t update that campaign. Please try again.'),
      );
    }
  }

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1>Campaigns</h1>
          <p className="muted">
            Fundraising campaigns and their public donate pages.
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

      <section className="section-gap" aria-labelledby="campaigns-heading">
        <h2 id="campaigns-heading">All campaigns</h2>
        {campaigns.length === 0 ? (
          <div className="empty">
            <div className="empty-icon" aria-hidden="true">
              📣
            </div>
            <h3>No campaigns yet</h3>
            <p>
              {canManage
                ? 'Create your first campaign using the form below to start accepting gifts.'
                : 'Campaigns will appear here once an administrator creates one.'}
            </p>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="report-table">
              <thead>
                <tr>
                  <th scope="col">Campaign</th>
                  <th scope="col">Goal</th>
                  <th scope="col">Status</th>
                  <th scope="col">Public</th>
                  <th scope="col">Progress</th>
                  {canManage && <th scope="col">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <span className="signup-name">{c.title}</span>
                      <br />
                      <span className="muted">/{c.slug}</span>
                    </td>
                    <td className="num">
                      {c.goal_minor_units > 0
                        ? formatMinor(c.goal_minor_units, c.currency)
                        : '—'}
                    </td>
                    <td>
                      <span className={STATUS_PILL[c.status]}>
                        {statusLabel(c.status)}
                      </span>
                    </td>
                    <td>
                      <span
                        className={
                          c.is_public
                            ? 'pill pill-open'
                            : 'pill pill-neutral'
                        }
                      >
                        {c.is_public ? 'Public' : 'Private'}
                      </span>
                    </td>
                    <td>
                      <span
                        className={
                          c.publish_progress
                            ? 'pill pill-open'
                            : 'pill pill-neutral'
                        }
                      >
                        {c.publish_progress ? 'Shown' : 'Hidden'}
                      </span>
                    </td>
                    {canManage && (
                      <td>
                        <div className="cms-actions">
                          <label className="sr-only" htmlFor={`status-${c.id}`}>
                            Status for {c.title}
                          </label>
                          <select
                            id={`status-${c.id}`}
                            className="cms-select cms-order"
                            value={c.status}
                            onChange={(e) =>
                              onPatch(
                                c.id,
                                { status: e.target.value as CampaignStatus },
                                `“${c.title}” set to ${statusLabel(
                                  e.target.value as CampaignStatus,
                                ).toLowerCase()}.`,
                              )
                            }
                          >
                            {STATUS_OPTIONS.map((s) => (
                              <option key={s.value} value={s.value}>
                                {s.label}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() =>
                              onPatch(
                                c.id,
                                { is_public: !c.is_public },
                                `“${c.title}” is now ${
                                  c.is_public ? 'private' : 'public'
                                }.`,
                              )
                            }
                          >
                            {c.is_public ? 'Make private' : 'Make public'}
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() =>
                              onPatch(
                                c.id,
                                { publish_progress: !c.publish_progress },
                                `Progress for “${c.title}” is now ${
                                  c.publish_progress ? 'hidden' : 'shown'
                                }.`,
                              )
                            }
                          >
                            {c.publish_progress
                              ? 'Hide progress'
                              : 'Show progress'}
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {canManage && (
        <CreateCampaignForm
          onCreated={async () => {
            setNotice('Campaign created.');
            await refresh();
          }}
          onAuthLost={() => router.replace('/login')}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create campaign — donation.manage only.
// ---------------------------------------------------------------------------
function CreateCampaignForm({
  onCreated,
  onAuthLost,
}: {
  onCreated: () => void | Promise<void>;
  onAuthLost: () => void;
}) {
  const slugId = useId();
  const titleId = useId();
  const descId = useId();
  const currencyId = useId();
  const goalId = useId();
  const suggestedId = useId();

  const [slug, setSlug] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [goal, setGoal] = useState('');
  const [suggested, setSuggested] = useState('25, 50, 100, 250');
  const [isPublic, setIsPublic] = useState(false);
  const [publishProgress, setPublishProgress] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    const s = slug.trim();
    const t = title.trim();
    if (!s) {
      setError('A URL slug is required.');
      return;
    }
    if (!t) {
      setError('A title is required.');
      return;
    }
    const cur = currency.trim().toUpperCase() || 'USD';

    let goalMinor: number | undefined;
    if (goal.trim()) {
      const parsed = parseDollarsToMinor(goal);
      if (parsed == null) {
        setError('Enter a goal like 5000 or 5000.00, or leave it blank.');
        return;
      }
      goalMinor = parsed;
    }

    // Suggested amounts: comma-separated major units → integer minor units.
    let suggestedMinor: number[] | undefined;
    if (suggested.trim()) {
      const parts = suggested.split(',').map((p) => p.trim()).filter(Boolean);
      const parsed = parts.map(parseDollarsToMinor);
      if (parsed.some((v) => v == null)) {
        setError('Suggested amounts must be numbers, e.g. "25, 50, 100".');
        return;
      }
      suggestedMinor = parsed as number[];
    }

    setBusy(true);
    try {
      await createCampaign({
        slug: s,
        title: t,
        description: description.trim() || undefined,
        currency: cur,
        goal_minor_units: goalMinor,
        suggested_amounts: suggestedMinor,
        is_public: isPublic,
        publish_progress: publishProgress,
      });
      setSlug('');
      setTitle('');
      setDescription('');
      setGoal('');
      setSuggested('25, 50, 100, 250');
      setIsPublic(false);
      setPublishProgress(false);
      await onCreated();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      setError(errText(err, 'We couldn’t create that campaign. Try again.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel section-gap" aria-labelledby="create-heading">
      <h2 id="create-heading">Create a campaign</h2>
      <form onSubmit={onSubmit} noValidate>
        <div className="cms-field-row">
          <div className="field cms-grow">
            <label htmlFor={titleId}>
              Title <span className="req">*</span>
            </label>
            <input
              id={titleId}
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div className="field cms-grow">
            <label htmlFor={slugId}>
              URL slug <span className="req">*</span>
            </label>
            <input
              id={slugId}
              type="text"
              placeholder="e.g. general"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
            />
          </div>
        </div>

        <div className="field">
          <label htmlFor={descId}>Description</label>
          <textarea
            id={descId}
            className="cms-textarea"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <div className="cms-field-row">
          <div className="field cms-level">
            <label htmlFor={currencyId}>Currency</label>
            <input
              id={currencyId}
              type="text"
              maxLength={3}
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
            />
          </div>
          <div className="field cms-grow">
            <label htmlFor={goalId}>Goal amount</label>
            <p className="hint">In {currency.toUpperCase() || 'USD'}. Optional.</p>
            <input
              id={goalId}
              type="text"
              inputMode="decimal"
              placeholder="5000"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
            />
          </div>
          <div className="field cms-grow">
            <label htmlFor={suggestedId}>Suggested amounts</label>
            <p className="hint">Comma-separated, e.g. 25, 50, 100.</p>
            <input
              id={suggestedId}
              type="text"
              value={suggested}
              onChange={(e) => setSuggested(e.target.value)}
            />
          </div>
        </div>

        <div className="check-row">
          <input
            id="create-public"
            type="checkbox"
            checked={isPublic}
            onChange={(e) => setIsPublic(e.target.checked)}
          />
          <div>
            <label htmlFor="create-public">Publish the public donate page</label>
            <p className="hint">Makes the campaign reachable at /donate.</p>
          </div>
        </div>
        <div className="check-row">
          <input
            id="create-progress"
            type="checkbox"
            checked={publishProgress}
            onChange={(e) => setPublishProgress(e.target.checked)}
          />
          <div>
            <label htmlFor="create-progress">Show a public progress bar</label>
            <p className="hint">
              Displays aggregate raised/goal totals — never donor names.
            </p>
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
          {busy ? 'Creating…' : 'Create campaign'}
        </button>
      </form>
    </section>
  );
}
