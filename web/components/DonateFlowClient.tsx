'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useEffect, useId, useState } from 'react';
import {
  ApiError,
  createDonation,
  getCampaign,
  getDonationStatus,
  type DonationKind,
  type PublicCampaign,
} from '@/lib/api';
import { formatMinor, parseDollarsToMinor } from '@/lib/money';

// The campaign is addressed by slug via ?campaign=; single-tenant orgs fall back
// to a conventional default so a bare /donate still works.
const DEFAULT_SLUG = 'general';

type LoadState =
  | { kind: 'loading' }
  | { kind: 'load-error'; message: string }
  | { kind: 'not-found' }
  | { kind: 'ready'; campaign: PublicCampaign };

type Step = 'amount' | 'details';

function isEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

// Server-status → friendly copy for POST failures. We keep the donor on the
// details step (recoverable) rather than crashing.
function submitErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 429) {
      return 'That’s a lot of requests in a short time. Please wait a moment and try again.';
    }
    if (err.status === 400) {
      return 'We couldn’t verify this request. Please refresh the page and try again.';
    }
    if (err.status === 404) {
      return 'This campaign is no longer accepting gifts.';
    }
    // 422 (validation) and anything else: prefer the server's detail.
    return err.message;
  }
  return 'We couldn’t reach the server. Please try again in a moment.';
}

export default function DonateFlowClient({
  // Anti-bot token. Empty in dev; a Turnstile widget can populate this later.
  botToken = '',
}: {
  botToken?: string;
}) {
  const params = useSearchParams();
  const slug = params.get('campaign')?.trim() || DEFAULT_SLUG;

  const [load, setLoad] = useState<LoadState>({ kind: 'loading' });

  // Step + captured data (pre-submit; the server owns money state, so none of
  // this is persisted until the donor submits).
  const [step, setStep] = useState<Step>('amount');
  const [amountMinor, setAmountMinor] = useState<number | null>(null);
  const [customText, setCustomText] = useState('');
  const [amountError, setAmountError] = useState('');
  const [kind, setKind] = useState<DonationKind>('one_time');
  const [designation, setDesignation] = useState('');

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [anonymous, setAnonymous] = useState(false);
  const [consent, setConsent] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  // Once set, we're in the redirecting state: poll status → hosted checkout.
  const [redirect, setRedirect] = useState<string | null>(null);

  const customId = useId();
  const nameId = useId();
  const emailId = useId();
  const desigId = useId();

  // Load the campaign once (per slug).
  useEffect(() => {
    let active = true;
    setLoad({ kind: 'loading' });
    getCampaign(slug)
      .then((campaign) => {
        if (!active) return;
        if (!campaign) {
          setLoad({ kind: 'not-found' });
          return;
        }
        setDesignation(campaign.designations[0]?.code ?? '');
        setLoad({ kind: 'ready', campaign });
      })
      .catch((err: unknown) => {
        if (!active) return;
        setLoad({
          kind: 'load-error',
          message:
            err instanceof ApiError
              ? err.message
              : 'We couldn’t load this campaign. Please refresh in a moment.',
        });
      });
    return () => {
      active = false;
    };
  }, [slug]);

  // Redirecting: poll the capability-token status until a hosted-checkout URL
  // appears, then hand the donor off. Card data is NEVER collected in our UI.
  useEffect(() => {
    if (!redirect) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = () => {
      getDonationStatus(redirect)
        .then((status) => {
          if (!active) return;
          if (status.checkout_url) {
            window.location.assign(status.checkout_url);
            return;
          }
          if (status.status === 'failed') {
            setRedirect(null);
            setSubmitting(false);
            setFormError(
              'We couldn’t start your payment. Please review your details and try again.',
            );
            return;
          }
          timer = setTimeout(poll, 1500);
        })
        .catch(() => {
          if (!active) return;
          // Transient network / 5xx: keep polling, the token is durable.
          timer = setTimeout(poll, 2000);
        });
    };
    poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [redirect]);

  if (load.kind === 'loading') {
    return (
      <div className="container page donate-narrow">
        <p role="status">Loading…</p>
      </div>
    );
  }

  if (load.kind === 'load-error') {
    return (
      <div className="container page donate-narrow">
        <h1>Make a donation</h1>
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t load this campaign</strong>
          <p>{load.message}</p>
        </div>
        <Link className="btn btn-secondary" href="/">
          Back to home
        </Link>
      </div>
    );
  }

  if (load.kind === 'not-found') {
    return (
      <div className="container page donate-narrow">
        <h1>Make a donation</h1>
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">
            🔍
          </div>
          <h2>Campaign not found</h2>
          <p>
            We couldn’t find this campaign. It may have closed, or the link may
            be out of date.
          </p>
          <Link className="btn btn-primary" href="/">
            Back to home
          </Link>
        </div>
      </div>
    );
  }

  const { campaign } = load;

  // Redirecting projection.
  if (redirect) {
    return (
      <div className="container page donate-narrow">
        <h1>{campaign.title}</h1>
        <div className="panel processing" role="status" aria-live="polite">
          <div className="spinner" aria-hidden="true" />
          <h2>Taking you to secure checkout…</h2>
          <p className="muted">
            Hold on while we hand you off to our payment provider. Don’t refresh
            or close this tab.
          </p>
        </div>
      </div>
    );
  }

  const designationLabel =
    campaign.designations.find((d) => d.code === designation)?.label ?? null;

  function goToDetails(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setAmountError('');
    // Prefer a typed custom amount, else the selected suggested amount.
    let effective = amountMinor;
    if (customText.trim()) {
      const parsed = parseDollarsToMinor(customText);
      if (parsed == null) {
        setAmountError('Enter an amount like 50 or 50.00.');
        return;
      }
      effective = parsed;
    }
    if (effective == null || effective <= 0) {
      setAmountError('Choose or enter an amount to give.');
      return;
    }
    setAmountMinor(effective);
    setStep('details');
  }

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError('');
    if (amountMinor == null || amountMinor <= 0) {
      setStep('amount');
      return;
    }
    if (!anonymous) {
      if (!name.trim()) {
        setFormError('Please enter your name, or choose to give anonymously.');
        return;
      }
      if (!isEmail(email)) {
        setFormError('Please enter a valid email so we can send your receipt.');
        return;
      }
    }
    setSubmitting(true);
    try {
      const result = await createDonation({
        campaign_slug: campaign.slug,
        amount_minor_units: amountMinor,
        kind,
        donor_name: name.trim(),
        donor_email: email.trim(),
        is_anonymous: anonymous,
        designation_code: designation,
        consent_marketing: consent,
        bot_token: botToken,
      });
      // Enter the redirecting state; the poll effect takes over. We keep
      // `submitting` true so the button never re-enables for a double-submit.
      setRedirect(result.token);
    } catch (err) {
      setFormError(submitErrorMessage(err));
      setSubmitting(false);
    }
  }

  const kindNoun = kind === 'recurring' ? 'monthly gift' : 'gift';

  return (
    <div className="container page donate-narrow">
      <h1>{campaign.title}</h1>

      <ol className="flow-steps" aria-label="Donation steps">
        <li
          className={`flow-step ${step === 'amount' ? 'is-current' : 'is-done'}`}
          aria-current={step === 'amount' ? 'step' : undefined}
        >
          Amount
        </li>
        <li
          className={`flow-step ${step === 'details' ? 'is-current' : ''}`}
          aria-current={step === 'details' ? 'step' : undefined}
        >
          Your details
        </li>
      </ol>

      {step === 'amount' && (
        <form onSubmit={goToDetails} noValidate>
          {campaign.description && (
            <p className="lede">{campaign.description}</p>
          )}

          {campaign.progress && <ProgressBar progress={campaign.progress} />}

          <section className="section-gap" aria-labelledby="amount-heading">
            <h2 id="amount-heading">Choose an amount</h2>
            <div
              className="amount-grid"
              role="group"
              aria-label="Suggested amounts"
            >
              {campaign.suggested_amounts.map((value) => (
                <button
                  key={value}
                  type="button"
                  className="amount-choice"
                  aria-pressed={!customText.trim() && amountMinor === value}
                  onClick={() => {
                    setAmountMinor(value);
                    setCustomText('');
                    setAmountError('');
                  }}
                >
                  {formatMinor(value, campaign.currency)}
                </button>
              ))}
            </div>

            <div className="field">
              <label htmlFor={customId}>Or enter a custom amount</label>
              <p className="hint" id={`${customId}-hint`}>
                Amount in {campaign.currency}, e.g. 75 or 75.00.
              </p>
              <input
                id={customId}
                type="text"
                inputMode="decimal"
                placeholder="0.00"
                value={customText}
                aria-describedby={`${customId}-hint`}
                aria-invalid={amountError ? true : undefined}
                onChange={(e) => {
                  setCustomText(e.target.value);
                  setAmountError('');
                  const parsed = parseDollarsToMinor(e.target.value);
                  setAmountMinor(parsed);
                }}
              />
              <div aria-live="assertive">
                {amountError && (
                  <p className="field-error" role="alert">
                    {amountError}
                  </p>
                )}
              </div>
            </div>

            <div className="seg" role="group" aria-label="Giving frequency">
              <button
                type="button"
                className="seg-btn"
                aria-pressed={kind === 'one_time'}
                onClick={() => setKind('one_time')}
              >
                One-time
              </button>
              <button
                type="button"
                className="seg-btn"
                aria-pressed={kind === 'recurring'}
                onClick={() => setKind('recurring')}
              >
                Monthly
              </button>
            </div>

            {campaign.designations.length > 0 && (
              <div className="field">
                <label htmlFor={desigId}>Direct my gift to</label>
                <select
                  id={desigId}
                  className="cms-select"
                  value={designation}
                  onChange={(e) => setDesignation(e.target.value)}
                >
                  {campaign.designations.map((d) => (
                    <option key={d.code} value={d.code}>
                      {d.label}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </section>

          <button type="submit" className="btn btn-primary btn-block">
            Continue
          </button>
        </form>
      )}

      {step === 'details' && amountMinor != null && (
        <form onSubmit={submit} noValidate>
          <div className="gift-summary">
            <span className="gift-amount">
              {formatMinor(amountMinor, campaign.currency)}
            </span>
            <span className="muted">
              {kind === 'recurring' ? 'per month' : 'one-time'}
              {designationLabel ? ` · ${designationLabel}` : ''}
            </span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setStep('amount')}
              disabled={submitting}
            >
              Change
            </button>
          </div>

          <div className="check-row">
            <input
              id="donate-anon"
              type="checkbox"
              checked={anonymous}
              onChange={(e) => setAnonymous(e.target.checked)}
            />
            <div>
              <label htmlFor="donate-anon">Give anonymously</label>
              <p className="hint">
                Your name won’t appear in any public acknowledgement.
              </p>
            </div>
          </div>

          <div className="field">
            <label htmlFor={nameId}>
              Full name {!anonymous && <span className="req">*</span>}
            </label>
            <input
              id={nameId}
              type="text"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor={emailId}>
              Email {!anonymous && <span className="req">*</span>}
            </label>
            <p className="hint">We’ll email your receipt here.</p>
            <input
              id={emailId}
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div className="check-row">
            <input
              id="donate-consent"
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            <div>
              <label htmlFor="donate-consent">
                Keep me updated by email
              </label>
              <p className="hint">
                Occasional news about the impact of your {kindNoun}. Optional.
              </p>
            </div>
          </div>

          {/* Anti-bot token slot (e.g. Turnstile). Hidden in dev; the value is
              supplied via the botToken prop and submitted with the donation. */}

          <div aria-live="assertive">
            {formError && (
              <div className="alert alert-danger" role="alert">
                <strong>We couldn’t process your gift</strong>
                <p>{formError}</p>
              </div>
            )}
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-block"
            disabled={submitting}
          >
            {submitting
              ? 'Processing…'
              : `Give ${formatMinor(amountMinor, campaign.currency)}${
                  kind === 'recurring' ? ' monthly' : ''
                }`}
          </button>

          <p className="donate-secure">
            <span aria-hidden="true">🔒</span>
            You’ll enter your card securely on our payment provider’s page — we
            never see or store your card details.
          </p>
        </form>
      )}
    </div>
  );
}

function ProgressBar({
  progress,
}: {
  progress: NonNullable<PublicCampaign['progress']>;
}) {
  const { raised_minor_units, goal_minor_units, currency } = progress;
  const pct =
    goal_minor_units > 0
      ? Math.min(100, Math.round((raised_minor_units / goal_minor_units) * 100))
      : 0;
  return (
    <div
      className="progress"
      role="group"
      aria-label="Fundraising progress"
    >
      <div className="progress-track">
        <div
          className="progress-fill"
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${pct}% of goal raised`}
        />
      </div>
      <p className="progress-caption">
        <span>
          <strong>{formatMinor(raised_minor_units, currency)}</strong> raised
        </span>
        <span>
          of <strong>{formatMinor(goal_minor_units, currency)}</strong> goal
        </span>
      </p>
    </div>
  );
}
