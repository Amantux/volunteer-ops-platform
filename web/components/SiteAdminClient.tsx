'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import {
  ApiError,
  createPage,
  getToken,
  listPages,
  type AdminPage,
} from '@/lib/auth';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; pages: AdminPage[] }
  | { kind: 'error'; message: string };

function isPublished(status: string): boolean {
  return status.trim().toLowerCase() === 'published';
}

function formatDateTime(value: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function SiteAdminClient() {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');

  const load = useCallback(() => {
    if (!getToken()) {
      router.replace('/login');
      return;
    }
    setState({ kind: 'loading' });
    listPages()
      .then((pages) => setState({ kind: 'ready', pages }))
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
              : 'We couldn’t load your pages. Please refresh in a moment.',
        });
      });
  }, [router]);

  useEffect(() => {
    load();
  }, [load]);

  async function onNewPage() {
    setCreateError('');
    const slug = window.prompt('Page address (slug), e.g. our-story');
    if (slug === null) return;
    const title = window.prompt('Page title, e.g. Our Story');
    if (title === null) return;
    if (!slug.trim() || !title.trim()) {
      setCreateError('A slug and a title are both required.');
      return;
    }
    setCreating(true);
    try {
      const { id } = await createPage({
        slug: slug.trim(),
        title: title.trim(),
      });
      router.push(`/admin/site/${id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.replace('/login');
        return;
      }
      setCreateError(
        err instanceof ApiError
          ? err.message
          : 'We couldn’t create that page. Please try again.',
      );
      setCreating(false);
    }
  }

  if (state.kind === 'loading') {
    return (
      <div className="container page">
        <p role="status">Loading your pages…</p>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className="container page">
        <h1>Site pages</h1>
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t load your pages</strong>
          <p>{state.message}</p>
        </div>
      </div>
    );
  }

  const { pages } = state;

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1>Site pages</h1>
          <p className="muted">Build and publish pages for your public site.</p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={onNewPage}
          disabled={creating}
        >
          {creating ? 'Creating…' : 'New page'}
        </button>
      </div>

      {createError && (
        <p className="field-error" role="alert">
          {createError}
        </p>
      )}

      {pages.length === 0 ? (
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">
            🧱
          </div>
          <h2>No pages yet</h2>
          <p>
            Create your first page to start building your public site. You can
            save a draft and publish it whenever you’re ready.
          </p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onNewPage}
            disabled={creating}
          >
            {creating ? 'Creating…' : 'New page'}
          </button>
        </div>
      ) : (
        <ul className="card-list stack">
          {pages.map((p) => (
            <li className="card" key={p.id}>
              <Link className="card-link" href={`/admin/site/${p.id}`}>
                <div className="row-head">
                  <h2>{p.title}</h2>
                  <span
                    className={
                      isPublished(p.status)
                        ? 'pill pill-published'
                        : 'pill pill-draft'
                    }
                  >
                    {isPublished(p.status) ? 'Published' : 'Draft'}
                  </span>
                </div>
                <p className="muted" style={{ margin: 0 }}>
                  /{p.slug}
                </p>
                <p className="card-meta" style={{ marginTop: 'var(--space-2)' }}>
                  Updated{' '}
                  <time dateTime={p.updated_at ?? undefined}>
                    {formatDateTime(p.updated_at)}
                  </time>
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
