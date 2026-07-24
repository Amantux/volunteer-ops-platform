'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useId, useMemo, useState } from 'react';
import {
  ApiError,
  approvePost,
  createChannel,
  createPost,
  getMe,
  getToken,
  listChannels,
  listPosts,
  publishPost,
  schedulePost,
  submitPost,
  updatePost,
  type Me,
  type SocialChannel,
  type SocialPost,
  type SocialPostStatus,
} from '@/lib/auth';

// Permission keys (mirrors the backend contract).
const P_DRAFT = 'social.draft';
const P_MANAGE = 'social.manage';
const P_APPROVE = 'social.approve';
const P_PUBLISH = 'social.publish';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; me: Me; channels: SocialChannel[]; posts: SocialPost[] }
  | { kind: 'error'; message: string };

// Status → human label + pill class. Colour conveys severity tier (neutral /
// warning / success / danger); the label carries the exact stage. No accent
// (teal) here — that is reserved for the single primary action.
const STATUS_META: Record<
  SocialPostStatus,
  { label: string; pill: string }
> = {
  draft: { label: 'Draft', pill: 'pill-draft' },
  pending_approval: { label: 'Pending approval', pill: 'pill-waitlist' },
  approved: { label: 'Approved', pill: 'pill-open' },
  scheduled: { label: 'Scheduled', pill: 'pill-draft' },
  publishing: { label: 'Publishing…', pill: 'pill-waitlist' },
  published: { label: 'Published', pill: 'pill-published' },
  partially_published: {
    label: 'Partially published',
    pill: 'pill-waitlist',
  },
  failed: { label: 'Failed', pill: 'pill-danger' },
};

function statusMeta(status: SocialPostStatus) {
  return STATUS_META[status] ?? { label: status, pill: 'pill-draft' };
}

// Lifecycle predicates — which transitions the *post status* allows. These are
// AND-ed with the caller's permission before a button is shown.
const canEditStatus = (s: SocialPostStatus) =>
  s === 'draft' || s === 'pending_approval';
const canSubmitStatus = (s: SocialPostStatus) => s === 'draft';
const canApproveStatus = (s: SocialPostStatus) => s === 'pending_approval';
const canScheduleStatus = (s: SocialPostStatus) =>
  s === 'approved' || s === 'scheduled';
const canPublishStatus = (s: SocialPostStatus) =>
  s === 'approved' ||
  s === 'scheduled' ||
  s === 'failed' ||
  s === 'partially_published';

function errText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

export default function SocialAdminClient() {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: 'loading' });

  // Page-level async feedback (aria-live).
  const [actionError, setActionError] = useState('');
  const [actionNotice, setActionNotice] = useState('');

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
        const canManage = me.permissions.includes(P_MANAGE);
        // /channels and /posts both require social.manage; a draft-only user
        // still gets the composer, just without an existing-post list.
        const [channels, posts] = await Promise.all([
          canManage ? listChannels() : Promise.resolve<SocialChannel[]>([]),
          canManage ? listPosts() : Promise.resolve<SocialPost[]>([]),
        ]);
        setState({ kind: 'ready', me, channels, posts });
      })
      .catch((err: unknown) => {
        if (bounceOn401(err)) return;
        setState({
          kind: 'error',
          message: errText(
            err,
            'We couldn’t load your social posts. Please refresh in a moment.',
          ),
        });
      });
  }, [router, bounceOn401]);

  useEffect(() => {
    load();
  }, [load]);

  // Refresh just the posts list after an action, keeping me/channels.
  const refreshPosts = useCallback(async () => {
    try {
      const posts = await listPosts();
      setState((prev) =>
        prev.kind === 'ready' ? { ...prev, posts } : prev,
      );
    } catch (err) {
      if (bounceOn401(err)) return;
      // A refresh failure shouldn't wipe the page; surface it inline.
      setActionError(errText(err, 'We couldn’t refresh the posts list.'));
    }
  }, [bounceOn401]);

  if (state.kind === 'loading') {
    return (
      <div className="container page">
        <p role="status">Loading your social posts…</p>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className="container page">
        <h1>Social posts</h1>
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t load your social posts</strong>
          <p>{state.message}</p>
        </div>
      </div>
    );
  }

  const { me, channels, posts } = state;
  const can = (perm: string) => me.permissions.includes(perm);

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1>Social posts</h1>
          <p className="muted">
            Draft, approve and publish posts to your channels. Publishing always
            needs a human approval first.
          </p>
        </div>
        <Link className="btn btn-secondary" href="/dashboard">
          Back to dashboard
        </Link>
      </div>

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

      {can(P_DRAFT) && (
        <Composer
          channels={channels}
          onCreated={async (msg) => {
            setActionError('');
            setActionNotice(msg);
            await refreshPosts();
          }}
          onAuthLost={() => router.replace('/login')}
        />
      )}

      <section className="section-gap" aria-labelledby="posts-heading">
        <h2 id="posts-heading">Posts</h2>
        {posts.length === 0 ? (
          <div className="empty">
            <div className="empty-icon" aria-hidden="true">
              📣
            </div>
            <h2>No posts yet</h2>
            <p>
              {can(P_DRAFT)
                ? 'Write a post above and save it as a draft to get started. It won’t go anywhere until it’s approved and published.'
                : 'There are no social posts to review yet.'}
            </p>
          </div>
        ) : (
          <ul className="card-list stack">
            {posts.map((post) => (
              <PostCard
                key={post.id}
                post={post}
                channels={channels}
                me={me}
                onRefresh={refreshPosts}
                onNotice={(msg) => {
                  setActionError('');
                  setActionNotice(msg);
                }}
                onError={(msg) => {
                  setActionNotice('');
                  setActionError(msg);
                }}
                onAuthLost={() => router.replace('/login')}
              />
            ))}
          </ul>
        )}
      </section>

      {can(P_MANAGE) && (
        <ChannelsPanel
          channels={channels}
          onAdded={async (channel) => {
            setActionError('');
            setActionNotice(`Channel “${channel.handle}” added.`);
            setState((prev) =>
              prev.kind === 'ready'
                ? { ...prev, channels: [...prev.channels, channel] }
                : prev,
            );
          }}
          onAuthLost={() => router.replace('/login')}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Composer — author-written body or an AI-assisted draft. Never publishes.
// ---------------------------------------------------------------------------
function Composer({
  channels,
  onCreated,
  onAuthLost,
}: {
  channels: SocialChannel[];
  onCreated: (message: string) => void | Promise<void>;
  onAuthLost: () => void;
}) {
  const bodyId = useId();
  const countId = useId();
  const promptId = useId();

  const [body, setBody] = useState('');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [saving, setSaving] = useState(false);
  const [localError, setLocalError] = useState('');

  const [aiOpen, setAiOpen] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [drafting, setDrafting] = useState(false);

  const selectableChannels = channels.filter((c) => c.enabled);

  // Smallest char limit among the selected channels drives the danger threshold.
  const limit = useMemo(() => {
    const limits = channels
      .filter((c) => selected.has(c.id))
      .map((c) => c.char_limit)
      .filter((n) => n > 0);
    return limits.length ? Math.min(...limits) : null;
  }, [channels, selected]);

  const over = limit !== null && body.length > limit;

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function validate(requireBody: boolean): string | null {
    if (selected.size === 0) return 'Choose at least one channel to post to.';
    if (requireBody && !body.trim()) return 'Write the post body first.';
    if (over)
      return `The post is over the ${limit}-character limit of the smallest selected channel. Shorten it or remove that channel.`;
    return null;
  }

  const channelIds = () => Array.from(selected);

  function reset() {
    setBody('');
    setSelected(new Set());
    setPrompt('');
    setAiOpen(false);
    setLocalError('');
  }

  async function onSaveDraft() {
    setLocalError('');
    const problem = validate(true);
    if (problem) {
      setLocalError(problem);
      return;
    }
    setSaving(true);
    try {
      await createPost({
        body: body.trim(),
        channel_ids: channelIds(),
        use_ai: false,
        prompt: '',
      });
      reset();
      await onCreated('Draft saved.');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      setLocalError(errText(err, 'We couldn’t save the draft. Please try again.'));
    } finally {
      setSaving(false);
    }
  }

  async function onDraftWithAi() {
    setLocalError('');
    if (selected.size === 0) {
      setLocalError('Choose at least one channel first.');
      return;
    }
    if (!prompt.trim()) {
      setLocalError('Add a short brief, e.g. “thank our weekend volunteers”.');
      return;
    }
    setDrafting(true);
    try {
      await createPost({
        body: body.trim(),
        channel_ids: channelIds(),
        use_ai: true,
        prompt: prompt.trim(),
      });
      reset();
      await onCreated(
        'AI-assisted draft created. Review and edit it below before submitting — you’re responsible for it.',
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      setLocalError(
        errText(err, 'We couldn’t draft that. Please try again.'),
      );
    } finally {
      setDrafting(false);
    }
  }

  const busy = saving || drafting;

  return (
    <section className="panel section-gap" aria-labelledby="composer-heading">
      <h2 id="composer-heading">Write a post</h2>

      <div className="field">
        <label htmlFor={bodyId}>Post body</label>
        <textarea
          id={bodyId}
          className="cms-textarea"
          rows={4}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          aria-describedby={countId}
          placeholder="What do you want to share?"
        />
        <p
          id={countId}
          className={`social-charcount${over ? ' social-charcount-over' : ''}`}
          role="status"
          aria-live="polite"
        >
          {body.length} characters
          {limit !== null
            ? ` — ${limit} allowed on the smallest selected channel${
                over ? ' (over the limit)' : ''
              }`
            : ''}
        </p>
      </div>

      <fieldset className="social-channels">
        <legend>Post to</legend>
        {selectableChannels.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            No channels yet. Add one in “Channels” below.
          </p>
        ) : (
          selectableChannels.map((c) => (
            <label className="cms-check" key={c.id}>
              <input
                type="checkbox"
                checked={selected.has(c.id)}
                onChange={() => toggle(c.id)}
              />
              {c.display_name || c.handle}{' '}
              <span className="muted">
                ({c.handle} · {c.char_limit} chars)
              </span>
            </label>
          ))
        )}
      </fieldset>

      {localError && (
        <p className="field-error" role="alert">
          {localError}
        </p>
      )}

      <div className="social-actions" style={{ borderTop: 'none', paddingTop: 0 }}>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => void onSaveDraft()}
          disabled={busy}
        >
          {saving ? 'Saving…' : 'Save draft'}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => setAiOpen((v) => !v)}
          disabled={busy}
          aria-expanded={aiOpen}
        >
          ✨ Help me write
        </button>
      </div>

      {aiOpen && (
        <div className="cms-assist-panel" style={{ marginTop: 'var(--space-3)' }}>
          <div className="field">
            <label htmlFor={promptId}>Brief for the AI draft</label>
            <input
              id={promptId}
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. “invite people to Saturday’s beach clean-up”"
            />
            <p className="hint">
              Creates an AI-assisted draft on the selected channels. It stays a
              draft — a person reviews and approves it before anything is
              published.
            </p>
          </div>
          <div className="cms-assist-actions">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => void onDraftWithAi()}
              disabled={busy}
            >
              {drafting ? 'Drafting…' : 'Draft with AI'}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setAiOpen(false)}
              disabled={busy}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// A single post card: status, body, per-channel targets, and the lifecycle
// actions gated by BOTH status and permission.
// ---------------------------------------------------------------------------
function PostCard({
  post,
  channels,
  me,
  onRefresh,
  onNotice,
  onError,
  onAuthLost,
}: {
  post: SocialPost;
  channels: SocialChannel[];
  me: Me;
  onRefresh: () => Promise<void>;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onAuthLost: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [scheduleAt, setScheduleAt] = useState('');

  const [editBody, setEditBody] = useState(post.body);
  const [editSelected, setEditSelected] = useState<Set<number>>(
    () => new Set(post.targets.map((t) => t.channel_id)),
  );

  const editBodyId = useId();
  const scheduleId = useId();

  const can = (perm: string) => me.permissions.includes(perm);
  const meta = statusMeta(post.status);
  const isAi = post.source === 'llm_assisted';

  const channelName = useCallback(
    (id: number) => {
      const c = channels.find((ch) => ch.id === id);
      return c ? c.display_name || c.handle : `Channel ${id}`;
    },
    [channels],
  );

  // Run a lifecycle action, refresh, and surface the outcome.
  async function run(
    fn: () => Promise<SocialPost>,
    successMsg: string,
  ) {
    setBusy(true);
    try {
      await fn();
      onNotice(successMsg);
      await onRefresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      onError(errText(err, 'That action didn’t work. Please try again.'));
    } finally {
      setBusy(false);
    }
  }

  function toggleEditChannel(id: number) {
    setEditSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function onSaveEdit() {
    if (!editBody.trim()) {
      onError('The post body can’t be empty.');
      return;
    }
    if (editSelected.size === 0) {
      onError('Choose at least one channel.');
      return;
    }
    setBusy(true);
    try {
      await updatePost(post.id, {
        body: editBody.trim(),
        channel_ids: Array.from(editSelected),
      });
      setEditing(false);
      onNotice('Post updated.');
      await onRefresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      onError(errText(err, 'We couldn’t update the post. Please try again.'));
    } finally {
      setBusy(false);
    }
  }

  async function onConfirmSchedule() {
    if (!scheduleAt) {
      onError('Pick a date and time to schedule.');
      return;
    }
    const when = new Date(scheduleAt);
    if (Number.isNaN(when.getTime())) {
      onError('That date and time isn’t valid.');
      return;
    }
    await run(
      () => schedulePost(post.id, when.toISOString()),
      'Post scheduled.',
    );
    setScheduling(false);
    setScheduleAt('');
  }

  // Which buttons to show: status allows it AND the user holds the permission.
  const showEdit = can(P_MANAGE) && canEditStatus(post.status);
  const showSubmit = can(P_MANAGE) && canSubmitStatus(post.status);
  const showApprove = can(P_APPROVE) && canApproveStatus(post.status);
  const showSchedule = can(P_MANAGE) && canScheduleStatus(post.status);
  const showPublish = can(P_PUBLISH) && canPublishStatus(post.status);
  const isRetry =
    post.status === 'failed' || post.status === 'partially_published';

  return (
    <li className="card">
      <div className="card-link" style={{ cursor: 'default' }}>
        <div className="row-head">
          <span className={`pill ${meta.pill}`}>{meta.label}</span>
          {isAi && (
            <span className="social-badge" title="Drafted with AI assistance">
              ✨ AI-assisted draft
            </span>
          )}
        </div>

        {isAi && (
          <p className="muted" style={{ margin: 'var(--space-2) 0 0' }}>
            Written with AI help — a person is responsible for reviewing it
            before it’s published.
          </p>
        )}

        {editing ? (
          <div style={{ marginTop: 'var(--space-3)' }}>
            <div className="field">
              <label htmlFor={editBodyId}>Post body</label>
              <textarea
                id={editBodyId}
                className="cms-textarea"
                rows={4}
                value={editBody}
                onChange={(e) => setEditBody(e.target.value)}
              />
            </div>
            <fieldset className="social-channels">
              <legend>Post to</legend>
              {channels
                .filter((c) => c.enabled || editSelected.has(c.id))
                .map((c) => (
                  <label className="cms-check" key={c.id}>
                    <input
                      type="checkbox"
                      checked={editSelected.has(c.id)}
                      onChange={() => toggleEditChannel(c.id)}
                    />
                    {c.display_name || c.handle}{' '}
                    <span className="muted">({c.char_limit} chars)</span>
                  </label>
                ))}
            </fieldset>
            <div className="social-actions" style={{ borderTop: 'none', paddingTop: 0 }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => void onSaveEdit()}
                disabled={busy}
              >
                {busy ? 'Saving…' : 'Save changes'}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setEditing(false);
                  setEditBody(post.body);
                  setEditSelected(
                    new Set(post.targets.map((t) => t.channel_id)),
                  );
                }}
                disabled={busy}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <p className="social-post-body">{post.body || <em>(empty)</em>}</p>
        )}

        <ul className="social-targets">
          {post.targets.map((t) => (
            <li className="social-target" key={t.channel_id}>
              <strong>{channelName(t.channel_id)}</strong>
              <span className="muted">{t.status}</span>
              {t.external_ref && (
                <span className="muted">ref: {t.external_ref}</span>
              )}
              {t.error && (
                <span className="social-target-error">⚠ {t.error}</span>
              )}
            </li>
          ))}
        </ul>

        {post.scheduled_at && (
          <p className="muted" style={{ margin: 'var(--space-2) 0 0' }}>
            Scheduled for{' '}
            <time dateTime={post.scheduled_at}>
              {new Date(post.scheduled_at).toLocaleString('en-GB')}
            </time>
          </p>
        )}

        {!editing &&
          (showEdit ||
            showSubmit ||
            showApprove ||
            showSchedule ||
            showPublish) && (
            <div className="social-actions">
              {showEdit && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setEditing(true)}
                  disabled={busy}
                >
                  Edit
                </button>
              )}
              {showSubmit && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() =>
                    void run(
                      () => submitPost(post.id),
                      'Submitted for approval.',
                    )
                  }
                  disabled={busy}
                >
                  Submit for approval
                </button>
              )}
              {showApprove && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() =>
                    void run(() => approvePost(post.id), 'Post approved.')
                  }
                  disabled={busy}
                >
                  Approve
                </button>
              )}
              {showSchedule && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setScheduling((v) => !v)}
                  disabled={busy}
                  aria-expanded={scheduling}
                >
                  Schedule
                </button>
              )}
              {showPublish && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() =>
                    void run(
                      () => publishPost(post.id),
                      isRetry
                        ? 'Re-publishing the failed channels.'
                        : 'Publishing now.',
                    )
                  }
                  disabled={busy}
                >
                  {isRetry ? 'Retry publish' : 'Publish now'}
                </button>
              )}
            </div>
          )}

        {scheduling && showSchedule && (
          <div className="social-schedule">
            <div className="field" style={{ marginBottom: 0 }}>
              <label htmlFor={scheduleId}>Publish at</label>
              <input
                id={scheduleId}
                type="datetime-local"
                value={scheduleAt}
                onChange={(e) => setScheduleAt(e.target.value)}
              />
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => void onConfirmSchedule()}
              disabled={busy}
            >
              {busy ? 'Scheduling…' : 'Confirm schedule'}
            </button>
          </div>
        )}
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Channels panel — list + add-channel form. "manual" only, for now.
// ---------------------------------------------------------------------------
function ChannelsPanel({
  channels,
  onAdded,
  onAuthLost,
}: {
  channels: SocialChannel[];
  onAdded: (channel: SocialChannel) => void | Promise<void>;
  onAuthLost: () => void;
}) {
  const handleId = useId();
  const nameId = useId();
  const limitId = useId();

  const [handle, setHandle] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [charLimit, setCharLimit] = useState('');
  const [saving, setSaving] = useState(false);
  const [localError, setLocalError] = useState('');

  async function onAdd() {
    setLocalError('');
    if (!handle.trim()) {
      setLocalError('A handle is required.');
      return;
    }
    const limit = charLimit.trim() ? Number(charLimit) : undefined;
    if (limit !== undefined && (!Number.isFinite(limit) || limit <= 0)) {
      setLocalError('Character limit must be a positive number.');
      return;
    }
    setSaving(true);
    try {
      const { id } = await createChannel({
        handle: handle.trim(),
        display_name: displayName.trim() || undefined,
        char_limit: limit,
      });
      await onAdded({
        id,
        platform: 'manual',
        handle: handle.trim(),
        display_name: displayName.trim(),
        enabled: true,
        char_limit: limit ?? 0,
      });
      setHandle('');
      setDisplayName('');
      setCharLimit('');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      setLocalError(
        errText(err, 'We couldn’t add that channel. Please try again.'),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel section-gap" aria-labelledby="channels-heading">
      <h2 id="channels-heading">Channels</h2>
      <p className="muted">
        “Manual” channels mean we record the post as published and give you the
        copy to paste yourself. Direct platform connections are coming later.
      </p>

      {channels.length > 0 && (
        <ul className="plain-list" style={{ margin: 'var(--space-4) 0' }}>
          {channels.map((c) => (
            <li key={c.id}>
              <span>
                <strong>{c.display_name || c.handle}</strong>{' '}
                <span className="muted">
                  {c.handle} · {c.platform} · {c.char_limit} chars
                </span>
              </span>
              <span className={`pill ${c.enabled ? 'pill-open' : 'pill-draft'}`}>
                {c.enabled ? 'Enabled' : 'Disabled'}
              </span>
            </li>
          ))}
        </ul>
      )}

      <h3 className="section-gap">Add a channel</h3>
      <div className="field">
        <label htmlFor={handleId}>Handle</label>
        <input
          id={handleId}
          type="text"
          value={handle}
          onChange={(e) => setHandle(e.target.value)}
          placeholder="@our-charity"
        />
      </div>
      <div className="field">
        <label htmlFor={nameId}>Display name (optional)</label>
        <input
          id={nameId}
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="Our Charity on Instagram"
        />
      </div>
      <div className="field cms-order">
        <label htmlFor={limitId}>Character limit (optional)</label>
        <input
          id={limitId}
          type="number"
          inputMode="numeric"
          min={1}
          value={charLimit}
          onChange={(e) => setCharLimit(e.target.value)}
          placeholder="280"
        />
      </div>
      {localError && (
        <p className="field-error" role="alert">
          {localError}
        </p>
      )}
      <button
        type="button"
        className="btn btn-secondary"
        onClick={() => void onAdd()}
        disabled={saving}
      >
        {saving ? 'Adding…' : 'Add channel'}
      </button>
    </section>
  );
}
