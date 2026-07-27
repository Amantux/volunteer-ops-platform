'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useId, useState } from 'react';
import {
  ApiError,
  exportDonationsCsv,
  getDonationMetrics,
  getMe,
  getToken,
  listDonations,
  recordInKind,
  type Donation,
  type DonationMetrics,
  type Me,
} from '@/lib/auth';
import { formatMinor, parseDollarsToMinor } from '@/lib/money';
import type { DonationKind } from '@/lib/api';

const P_VIEW = 'donation.view';
const P_MANAGE = 'donation.manage';
const P_EXPORT = 'finance.export';

type State =
  | { kind: 'loading' }
  | {
      kind: 'ready';
      me: Me;
      metrics: DonationMetrics;
      donations: Donation[];
    }
  | { kind: 'no-access'; me: Me }
  | { kind: 'error'; message: string };

const KIND_PILL: Record<DonationKind, string> = {
  one_time: 'pill pill-neutral',
  recurring: 'pill pill-open',
};

// Donation status → pill class. Meaning is carried by the label, not colour.
function statusPill(status: string): string {
  const s = status.toLowerCase();
  if (s === 'succeeded' || s === 'active') return 'pill pill-open';
  if (s === 'failed' || s === 'refunded') return 'pill pill-danger';
  if (s === 'pending' || s === 'processing') return 'pill pill-waitlist';
  return 'pill pill-neutral';
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

function errText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

export default function DonationsClient() {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [notice, setNotice] = useState('');
  const [actionError, setActionError] = useState('');
  const [downloading, setDownloading] = useState(false);

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
        const [metrics, donations] = await Promise.all([
          getDonationMetrics(),
          listDonations(),
        ]);
        setState({ kind: 'ready', me, metrics, donations });
      })
      .catch((err: unknown) => {
        if (bounceOn401(err)) return;
        setState({
          kind: 'error',
          message: errText(
            err,
            'We couldn’t load donations. Please refresh in a moment.',
          ),
        });
      });
  }, [router, bounceOn401]);

  useEffect(() => {
    load();
  }, [load]);

  const refresh = useCallback(async () => {
    try {
      const [metrics, donations] = await Promise.all([
        getDonationMetrics(),
        listDonations(),
      ]);
      setState((prev) =>
        prev.kind === 'ready' ? { ...prev, metrics, donations } : prev,
      );
    } catch (err) {
      if (bounceOn401(err)) return;
      setActionError(errText(err, 'We couldn’t refresh donations.'));
    }
  }, [bounceOn401]);

  async function onDownloadCsv() {
    setNotice('');
    setActionError('');
    setDownloading(true);
    try {
      const blob = await exportDonationsCsv();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'donations.csv';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setNotice('Your CSV export has started downloading.');
    } catch (err) {
      if (bounceOn401(err)) return;
      setActionError(
        errText(err, 'We couldn’t generate the CSV export. Please try again.'),
      );
    } finally {
      setDownloading(false);
    }
  }

  if (state.kind === 'loading') {
    return (
      <div className="container page">
        <p role="status">Loading donations…</p>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className="container page">
        <h1>Donations</h1>
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t load donations</strong>
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
            <h1>Donations</h1>
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
            Viewing donations needs the “donation.view” permission, which your
            account doesn’t have. Ask an administrator to grant it.
          </p>
        </div>
      </div>
    );
  }

  const { me, metrics, donations } = state;
  const canManage = me.permissions.includes(P_MANAGE);
  const canExport = me.permissions.includes(P_EXPORT);
  // A representative currency for the KPI cards (donations are single-currency
  // per org in practice); fall back to USD when there are no rows yet.
  const cur = donations[0]?.currency ?? 'USD';

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1>Donations</h1>
          <p className="muted">Gifts, recurring plans, and finance totals.</p>
        </div>
        <div className="cms-actions">
          {canExport && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onDownloadCsv}
              disabled={downloading}
            >
              {downloading ? 'Preparing…' : 'Download CSV'}
            </button>
          )}
          <Link className="btn btn-secondary" href="/dashboard">
            Back to dashboard
          </Link>
        </div>
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

      <div className="panel">
        <div className="metric-grid">
          <Kpi label="Total volume" value={formatMinor(metrics.volume_minor_units, cur)} />
          <Kpi label="Donations" value={String(metrics.donation_count)} />
          <Kpi label="Donors" value={String(metrics.donor_count)} />
          <Kpi
            label="Average gift"
            value={formatMinor(metrics.average_minor_units, cur)}
          />
          <Kpi
            label="Refunded"
            value={formatMinor(metrics.refunded_minor_units, cur)}
          />
          <Kpi
            label="Recurring plans"
            value={String(metrics.active_recurring_plans)}
          />
          <Kpi
            label="Recurring MRR"
            value={formatMinor(metrics.recurring_mrr_minor_units, cur)}
          />
        </div>
      </div>

      <section className="section-gap" aria-labelledby="donations-heading">
        <h2 id="donations-heading">Recent donations</h2>
        {donations.length === 0 ? (
          <div className="empty">
            <div className="empty-icon" aria-hidden="true">
              💝
            </div>
            <h3>No donations yet</h3>
            <p>
              Gifts appear here as soon as your first donor completes checkout on
              the public donate page.
            </p>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="report-table">
              <thead>
                <tr>
                  <th scope="col">Donor</th>
                  <th scope="col" className="num">
                    Amount
                  </th>
                  <th scope="col">Type</th>
                  <th scope="col">Status</th>
                  <th scope="col">Date</th>
                </tr>
              </thead>
              <tbody>
                {donations.map((d) => (
                  <tr key={d.id}>
                    <td>{d.donor_name}</td>
                    <td className="num">
                      {formatMinor(d.amount_minor_units, d.currency)}
                    </td>
                    <td>
                      <span className={KIND_PILL[d.kind]}>
                        {d.kind === 'recurring' ? 'Monthly' : 'One-time'}
                      </span>
                    </td>
                    <td>
                      <span className={statusPill(d.status)}>{d.status}</span>
                    </td>
                    <td>{formatDate(d.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {canManage && (
        <InKindForm
          onRecorded={async () => {
            setNotice('In-kind gift recorded.');
            await refresh();
          }}
          onAuthLost={() => router.replace('/login')}
        />
      )}
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span className="metric-value">{value}</span>
      <span className="metric-label">{label}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Record an in-kind (non-cash) gift — donation.manage only.
// ---------------------------------------------------------------------------
function InKindForm({
  onRecorded,
  onAuthLost,
}: {
  onRecorded: () => void | Promise<void>;
  onAuthLost: () => void;
}) {
  const descId = useId();
  const donorId = useId();
  const emailId = useId();
  const receivedId = useId();
  const valueId = useId();
  const currencyId = useId();
  const campaignId = useId();

  const [description, setDescription] = useState('');
  const [donorName, setDonorName] = useState('');
  const [donorEmail, setDonorEmail] = useState('');
  const [received, setReceived] = useState('');
  const [value, setValue] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [campaign, setCampaign] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    const desc = description.trim();
    const donor = donorName.trim();
    if (!desc) {
      setError('A description of the gift is required.');
      return;
    }
    if (!donor) {
      setError('A donor name is required.');
      return;
    }
    if (!received) {
      setError('A received date is required.');
      return;
    }
    const receivedDate = new Date(received);
    if (Number.isNaN(receivedDate.getTime())) {
      setError('Enter a valid received date.');
      return;
    }

    let valueMinor: number | undefined;
    if (value.trim()) {
      const parsed = parseDollarsToMinor(value);
      if (parsed == null) {
        setError('Estimated value must be a number, or leave it blank.');
        return;
      }
      valueMinor = parsed;
    }

    let campaignIdNum: number | undefined;
    if (campaign.trim()) {
      const n = Number(campaign);
      if (!Number.isInteger(n) || n < 1) {
        setError('Campaign ID must be a whole number, or leave it blank.');
        return;
      }
      campaignIdNum = n;
    }

    setBusy(true);
    try {
      await recordInKind({
        description: desc,
        received_at: receivedDate.toISOString(),
        donor_name: donor,
        donor_email: donorEmail.trim() || undefined,
        estimated_value_minor_units: valueMinor,
        currency: currency.trim().toUpperCase() || 'USD',
        campaign_id: campaignIdNum,
      });
      setDescription('');
      setDonorName('');
      setDonorEmail('');
      setReceived('');
      setValue('');
      setCampaign('');
      await onRecorded();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      setError(errText(err, 'We couldn’t record that gift. Try again.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel section-gap" aria-labelledby="inkind-heading">
      <h2 id="inkind-heading">Record an in-kind gift</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Log a non-cash donation (goods or services) for your records.
      </p>
      <form onSubmit={onSubmit} noValidate>
        <div className="field">
          <label htmlFor={descId}>
            Description <span className="req">*</span>
          </label>
          <input
            id={descId}
            type="text"
            placeholder="e.g. 20 boxes of canned food"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        <div className="cms-field-row">
          <div className="field cms-grow">
            <label htmlFor={donorId}>
              Donor name <span className="req">*</span>
            </label>
            <input
              id={donorId}
              type="text"
              value={donorName}
              onChange={(e) => setDonorName(e.target.value)}
            />
          </div>
          <div className="field cms-grow">
            <label htmlFor={emailId}>Donor email</label>
            <input
              id={emailId}
              type="email"
              value={donorEmail}
              onChange={(e) => setDonorEmail(e.target.value)}
            />
          </div>
          <div className="field cms-grow">
            <label htmlFor={receivedId}>
              Received <span className="req">*</span>
            </label>
            <input
              id={receivedId}
              type="date"
              value={received}
              onChange={(e) => setReceived(e.target.value)}
            />
          </div>
        </div>
        <div className="cms-field-row">
          <div className="field cms-grow">
            <label htmlFor={valueId}>Estimated value</label>
            <p className="hint">In {currency.toUpperCase() || 'USD'}. Optional.</p>
            <input
              id={valueId}
              type="text"
              inputMode="decimal"
              placeholder="250"
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          </div>
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
          <div className="field cms-level">
            <label htmlFor={campaignId}>Campaign ID</label>
            <input
              id={campaignId}
              type="number"
              min="1"
              step="1"
              inputMode="numeric"
              value={campaign}
              onChange={(e) => setCampaign(e.target.value)}
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
          {busy ? 'Recording…' : 'Record in-kind gift'}
        </button>
      </form>
    </section>
  );
}
