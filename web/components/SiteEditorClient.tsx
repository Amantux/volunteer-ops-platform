'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import PageBlocks from '@/components/PageBlocks';
import type { PageBlock } from '@/lib/api';
import {
  ApiError,
  assistCopy,
  getMe,
  getPage,
  getToken,
  publishPage,
  unpublishPage,
  updatePage,
  type AdminPage,
} from '@/lib/auth';

// ---------------------------------------------------------------------------
// Editor block model. Each block carries a stable local `id` for React keys and
// reordering. html/embed content is edited as a single `html` string; on save
// it is sent under key `html` (the server re-sanitizes — see the round-trip
// rule) and on load it is read from `safe_html` / `raw_html`.
// ---------------------------------------------------------------------------
type EditorBlock =
  | { id: string; type: 'heading'; level: number; text: string }
  | { id: string; type: 'paragraph'; text: string }
  | { id: string; type: 'image'; url: string; alt: string }
  | { id: string; type: 'button'; label: string; href: string }
  | { id: string; type: 'divider' }
  | { id: string; type: 'html'; html: string }
  | { id: string; type: 'embed'; html: string };

type BlockType = EditorBlock['type'];

const BASE_BLOCK_TYPES: { type: BlockType; label: string }[] = [
  { type: 'heading', label: 'Heading' },
  { type: 'paragraph', label: 'Paragraph' },
  { type: 'image', label: 'Image' },
  { type: 'button', label: 'Button' },
  { type: 'divider', label: 'Divider' },
];
const DEVELOP_BLOCK_TYPES: { type: BlockType; label: string }[] = [
  { type: 'html', label: 'Custom HTML' },
  { type: 'embed', label: 'Embed' },
];

// Plain text → paragraph HTML. If the author already typed HTML (contains a
// tag) it is sent as-is; otherwise blank-line-separated lines become <p>…</p>.
function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Paragraphs are plain text → <p>. Author-typed markup is escaped, so a paragraph block never
// carries raw HTML (the Custom HTML block is the escape hatch). Keeps preview == payload safe.
function paragraphToHtml(text: string): string {
  const t = text.trim();
  if (!t) return '';
  return t
    .split(/\n{2,}/)
    .map((para) => `<p>${escapeHtml(para).replace(/\n/g, '<br />')}</p>`)
    .join('');
}

function fromServer(block: PageBlock, id: string): EditorBlock | null {
  switch (block.type) {
    case 'heading':
      return { id, type: 'heading', level: block.level, text: block.text };
    case 'paragraph':
      return { id, type: 'paragraph', text: block.html };
    case 'image':
      return { id, type: 'image', url: block.url, alt: block.alt };
    case 'button':
      return { id, type: 'button', label: block.label, href: block.href };
    case 'divider':
      return { id, type: 'divider' };
    case 'html':
      return { id, type: 'html', html: block.safe_html };
    case 'embed':
      return { id, type: 'embed', html: block.raw_html };
    default:
      return null;
  }
}

function toPayload(block: EditorBlock): Record<string, unknown> {
  switch (block.type) {
    case 'heading':
      return { type: 'heading', level: block.level, text: block.text };
    case 'paragraph':
      return { type: 'paragraph', html: paragraphToHtml(block.text) };
    case 'image':
      return { type: 'image', url: block.url, alt: block.alt };
    case 'button':
      return { type: 'button', label: block.label, href: block.href };
    case 'divider':
      return { type: 'divider' };
    case 'html':
      return { type: 'html', html: block.html };
    case 'embed':
      return { type: 'embed', html: block.html };
  }
}

// Live-preview render shape. Note: for html/embed this shows the author's
// unsaved content BEFORE server sanitization; the "sanitized on save" note
// makes that explicit. embed still renders via the sandboxed iframe.
function toRenderBlock(block: EditorBlock): PageBlock {
  switch (block.type) {
    case 'heading':
      return { type: 'heading', level: block.level, text: block.text };
    case 'paragraph':
      return { type: 'paragraph', html: paragraphToHtml(block.text) };
    case 'image':
      return { type: 'image', url: block.url, alt: block.alt };
    case 'button':
      return { type: 'button', label: block.label, href: block.href };
    case 'divider':
      return { type: 'divider' };
    case 'html':
    case 'embed':
      // Preview shows the author's UNSANITIZED content (server sanitizes on save), so contain
      // both escape-hatch blocks in the sandboxed-iframe path — never feed raw input to the
      // `safe_html` field, whose invariant is "already server-sanitized".
      return { type: 'embed', raw_html: block.html };
  }
}

function defaultBlock(type: BlockType, id: string): EditorBlock {
  switch (type) {
    case 'heading':
      return { id, type: 'heading', level: 2, text: '' };
    case 'paragraph':
      return { id, type: 'paragraph', text: '' };
    case 'image':
      return { id, type: 'image', url: '', alt: '' };
    case 'button':
      return { id, type: 'button', label: '', href: '' };
    case 'divider':
      return { id, type: 'divider' };
    case 'html':
      return { id, type: 'html', html: '' };
    case 'embed':
      return { id, type: 'embed', html: '' };
  }
}

function isPublished(status: string): boolean {
  return status.trim().toLowerCase() === 'published';
}

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; page: AdminPage }
  | { kind: 'error'; message: string };

export default function SiteEditorClient({ id }: { id: string }) {
  const router = useRouter();
  const pageId = Number(id);

  const [state, setState] = useState<State>({ kind: 'loading' });
  const [canDevelop, setCanDevelop] = useState(false);

  const [title, setTitle] = useState('');
  const [blocks, setBlocks] = useState<EditorBlock[]>([]);
  const [customCss, setCustomCss] = useState('');
  const [showInNav, setShowInNav] = useState(false);
  const [navOrder, setNavOrder] = useState(0);

  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [notice, setNotice] = useState('');

  const [aiHints, setAiHints] = useState<Set<string>>(new Set());

  const idCounter = useRef(0);
  const genId = useCallback(() => {
    idCounter.current += 1;
    return `b${idCounter.current}`;
  }, []);

  useEffect(() => {
    if (!getToken()) {
      router.replace('/login');
      return;
    }
    if (!Number.isInteger(pageId) || pageId <= 0) {
      setState({ kind: 'error', message: 'That page address is not valid.' });
      return;
    }

    let active = true;
    Promise.all([getMe(), getPage(pageId)])
      .then(([me, page]) => {
        if (!active) return;
        setCanDevelop(me.permissions.includes('site.develop'));
        setTitle(page.title);
        setBlocks(
          page.blocks
            .map((b) => fromServer(b, genId()))
            .filter((b): b is EditorBlock => b !== null),
        );
        setCustomCss(page.custom_css);
        setShowInNav(page.show_in_nav);
        setNavOrder(page.nav_order);
        setState({ kind: 'ready', page });
      })
      .catch((err: unknown) => {
        if (!active) return;
        if (err instanceof ApiError && err.status === 401) {
          router.replace('/login');
          return;
        }
        setState({
          kind: 'error',
          message:
            err instanceof ApiError
              ? err.message
              : 'We couldn’t load this page. Please refresh in a moment.',
        });
      });
    return () => {
      active = false;
    };
  }, [pageId, router, genId]);

  function patchBlock(blockId: string, patch: Partial<EditorBlock>) {
    setBlocks((prev) =>
      prev.map((b) =>
        b.id === blockId ? ({ ...b, ...patch } as EditorBlock) : b,
      ),
    );
  }
  function addBlock(type: BlockType) {
    setBlocks((prev) => [...prev, defaultBlock(type, genId())]);
  }
  function removeBlock(blockId: string) {
    setBlocks((prev) => prev.filter((b) => b.id !== blockId));
  }
  function moveBlock(blockId: string, dir: -1 | 1) {
    setBlocks((prev) => {
      const i = prev.findIndex((b) => b.id === blockId);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  }
  function markAi(blockId: string) {
    setAiHints((prev) => new Set(prev).add(blockId));
  }

  const save = useCallback(async (): Promise<boolean> => {
    setSaveError('');
    setNotice('');
    setSaving(true);
    try {
      const updated = await updatePage(pageId, {
        title: title.trim(),
        blocks: blocks.map(toPayload),
        custom_css: customCss,
        show_in_nav: showInNav,
        nav_order: navOrder,
      });
      setState({ kind: 'ready', page: updated });
      setNotice('Draft saved.');
      return true;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.replace('/login');
        return false;
      }
      if (err instanceof ApiError && err.status === 403) {
        setSaveError(
          'Custom HTML/CSS needs the developer permission. Remove any custom HTML, embed and custom-CSS content, or ask an admin to grant it.',
        );
        return false;
      }
      setSaveError(
        err instanceof ApiError
          ? err.message
          : 'We couldn’t save this page. Please try again.',
      );
      return false;
    } finally {
      setSaving(false);
    }
  }, [pageId, title, blocks, customCss, showInNav, navOrder, router]);

  async function onPublish() {
    const ok = await save();
    if (!ok) return;
    setPublishing(true);
    try {
      const updated = await publishPage(pageId);
      setState({ kind: 'ready', page: updated });
      setNotice('Published — your page is now live.');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.replace('/login');
        return;
      }
      setSaveError(
        err instanceof ApiError
          ? err.message
          : 'We couldn’t publish this page. Please try again.',
      );
    } finally {
      setPublishing(false);
    }
  }

  async function onUnpublish() {
    setSaveError('');
    setNotice('');
    setPublishing(true);
    try {
      const updated = await unpublishPage(pageId);
      setState({ kind: 'ready', page: updated });
      setNotice('Unpublished — this page is no longer public.');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.replace('/login');
        return;
      }
      setSaveError(
        err instanceof ApiError
          ? err.message
          : 'We couldn’t unpublish this page. Please try again.',
      );
    } finally {
      setPublishing(false);
    }
  }

  if (state.kind === 'loading') {
    return (
      <div className="container page">
        <p role="status">Loading the editor…</p>
      </div>
    );
  }
  if (state.kind === 'error') {
    return (
      <div className="container page">
        <Link className="back-link" href="/admin/site">
          ← Back to all pages
        </Link>
        <h1>Editor</h1>
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t open this page</strong>
          <p>{state.message}</p>
        </div>
      </div>
    );
  }

  const { page } = state;
  const published = isPublished(page.status);
  const busy = saving || publishing;

  return (
    <div className="container page">
      <Link className="back-link" href="/admin/site">
        ← Back to all pages
      </Link>

      <div className="page-head">
        <div>
          <h1>Edit page</h1>
          <p className="muted" style={{ margin: 0 }}>
            /{page.slug}{' '}
            <span
              className={published ? 'pill pill-published' : 'pill pill-draft'}
            >
              {published ? 'Published' : 'Draft'}
            </span>
          </p>
        </div>
        <div className="cms-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void save()}
            disabled={busy}
          >
            {saving ? 'Saving…' : 'Save draft'}
          </button>
          {published ? (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void onUnpublish()}
              disabled={busy}
            >
              {publishing ? 'Working…' : 'Unpublish'}
            </button>
          ) : null}
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void onPublish()}
            disabled={busy}
          >
            {publishing ? 'Publishing…' : 'Publish'}
          </button>
        </div>
      </div>

      {notice && (
        <div className="alert alert-success" role="status">
          <p>{notice}</p>
        </div>
      )}
      {saveError && (
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t save this page</strong>
          <p>{saveError}</p>
        </div>
      )}

      <div className="cms-layout">
        <div className="cms-editor">
          <div className="field">
            <label htmlFor="page-title">Page title</label>
            <input
              id="page-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>

          <fieldset className="cms-settings">
            <legend>Navigation</legend>
            <label className="cms-check">
              <input
                type="checkbox"
                checked={showInNav}
                onChange={(e) => setShowInNav(e.target.checked)}
              />
              Show this page in the site menu
            </label>
            <div className="field cms-order">
              <label htmlFor="nav-order">Menu order</label>
              <input
                id="nav-order"
                type="number"
                inputMode="numeric"
                value={navOrder}
                onChange={(e) => setNavOrder(Number(e.target.value) || 0)}
              />
            </div>
          </fieldset>

          <h2 className="section-gap">Blocks</h2>

          {blocks.length === 0 && (
            <p className="muted">
              This page is empty. Add a block below to start building.
            </p>
          )}

          <ol className="cms-blocks">
            {blocks.map((block, i) => (
              <li className="cms-block" key={block.id}>
                <div className="cms-block-head">
                  <span className="cms-block-type">{blockTypeLabel(block)}</span>
                  <div className="cms-block-controls">
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => moveBlock(block.id, -1)}
                      disabled={i === 0}
                      aria-label="Move block up"
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => moveBlock(block.id, 1)}
                      disabled={i === blocks.length - 1}
                      aria-label="Move block down"
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => removeBlock(block.id)}
                      aria-label="Remove block"
                    >
                      Remove
                    </button>
                  </div>
                </div>

                <BlockFields
                  block={block}
                  onPatch={(patch) => patchBlock(block.id, patch)}
                  onAiFill={(text) => {
                    patchBlock(block.id, { text });
                    markAi(block.id);
                  }}
                  aiSuggested={aiHints.has(block.id)}
                />
              </li>
            ))}
          </ol>

          <div className="cms-add" role="group" aria-label="Add a block">
            <span className="cms-add-label">Add block:</span>
            {BASE_BLOCK_TYPES.map((t) => (
              <button
                key={t.type}
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => addBlock(t.type)}
              >
                + {t.label}
              </button>
            ))}
            {canDevelop &&
              DEVELOP_BLOCK_TYPES.map((t) => (
                <button
                  key={t.type}
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => addBlock(t.type)}
                >
                  + {t.label}
                </button>
              ))}
          </div>

          {canDevelop && (
            <div className="cms-develop">
              <h2 className="section-gap">Custom CSS</h2>
              <p className="cms-note muted">
                Custom HTML, embeds and CSS are sanitized on save. They apply on
                the live page.
              </p>
              <div className="field">
                <label htmlFor="custom-css" className="sr-only">
                  Custom CSS
                </label>
                <textarea
                  id="custom-css"
                  className="cms-textarea cms-code"
                  rows={6}
                  spellCheck={false}
                  value={customCss}
                  onChange={(e) => setCustomCss(e.target.value)}
                  placeholder="#page-… { }"
                />
              </div>
            </div>
          )}
        </div>

        <aside className="cms-preview" aria-label="Live preview">
          <h2>Preview</h2>
          <p className="cms-note muted">
            Content buttons and links are shown as they’ll appear live.
          </p>
          <div className="cms-preview-surface page-content">
            {blocks.length === 0 ? (
              <p className="muted">Nothing to preview yet.</p>
            ) : (
              <PageBlocks blocks={blocks.map(toRenderBlock)} />
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

function blockTypeLabel(block: EditorBlock): string {
  const all = [...BASE_BLOCK_TYPES, ...DEVELOP_BLOCK_TYPES];
  return all.find((t) => t.type === block.type)?.label ?? block.type;
}

function BlockFields({
  block,
  onPatch,
  onAiFill,
  aiSuggested,
}: {
  block: EditorBlock;
  onPatch: (patch: Partial<EditorBlock>) => void;
  onAiFill: (text: string) => void;
  aiSuggested: boolean;
}) {
  switch (block.type) {
    case 'heading':
      return (
        <div className="cms-block-body">
          <div className="cms-field-row">
            <div className="field cms-grow">
              <label htmlFor={`${block.id}-text`}>Heading text</label>
              <input
                id={`${block.id}-text`}
                type="text"
                value={block.text}
                onChange={(e) => onPatch({ text: e.target.value })}
              />
            </div>
            <div className="field cms-level">
              <label htmlFor={`${block.id}-level`}>Level</label>
              <select
                id={`${block.id}-level`}
                className="cms-select"
                value={block.level}
                onChange={(e) => onPatch({ level: Number(e.target.value) })}
              >
                <option value={1}>H1</option>
                <option value={2}>H2</option>
                <option value={3}>H3</option>
                <option value={4}>H4</option>
              </select>
            </div>
          </div>
          <AssistControl onAiFill={onAiFill} aiSuggested={aiSuggested} />
        </div>
      );
    case 'paragraph':
      return (
        <div className="cms-block-body">
          <div className="field">
            <label htmlFor={`${block.id}-text`}>Paragraph</label>
            <textarea
              id={`${block.id}-text`}
              className="cms-textarea"
              rows={4}
              value={block.text}
              onChange={(e) => onPatch({ text: e.target.value })}
            />
          </div>
          <AssistControl onAiFill={onAiFill} aiSuggested={aiSuggested} />
        </div>
      );
    case 'image':
      return (
        <div className="cms-block-body">
          <div className="field">
            <label htmlFor={`${block.id}-url`}>Image URL</label>
            <input
              id={`${block.id}-url`}
              type="url"
              value={block.url}
              onChange={(e) => onPatch({ url: e.target.value })}
              placeholder="https://…"
            />
          </div>
          <div className="field">
            <label htmlFor={`${block.id}-alt`}>Alt text</label>
            <input
              id={`${block.id}-alt`}
              type="text"
              value={block.alt}
              onChange={(e) => onPatch({ alt: e.target.value })}
            />
            <p className="hint">Describe the image for screen-reader users.</p>
          </div>
        </div>
      );
    case 'button':
      return (
        <div className="cms-block-body">
          <div className="field">
            <label htmlFor={`${block.id}-label`}>Button label</label>
            <input
              id={`${block.id}-label`}
              type="text"
              value={block.label}
              onChange={(e) => onPatch({ label: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor={`${block.id}-href`}>Link (href)</label>
            <input
              id={`${block.id}-href`}
              type="text"
              value={block.href}
              onChange={(e) => onPatch({ href: e.target.value })}
              placeholder="/our-story or https://…"
            />
          </div>
        </div>
      );
    case 'divider':
      return (
        <p className="muted cms-block-body" style={{ margin: 0 }}>
          A horizontal divider.
        </p>
      );
    case 'html':
      return (
        <div className="cms-block-body">
          <div className="field">
            <label htmlFor={`${block.id}-html`}>Custom HTML</label>
            <textarea
              id={`${block.id}-html`}
              className="cms-textarea cms-code"
              rows={4}
              spellCheck={false}
              value={block.html}
              onChange={(e) => onPatch({ html: e.target.value })}
            />
            <p className="hint">Sanitized on save.</p>
          </div>
        </div>
      );
    case 'embed':
      return (
        <div className="cms-block-body">
          <div className="field">
            <label htmlFor={`${block.id}-embed`}>Embed HTML</label>
            <textarea
              id={`${block.id}-embed`}
              className="cms-textarea cms-code"
              rows={4}
              spellCheck={false}
              value={block.html}
              onChange={(e) => onPatch({ html: e.target.value })}
            />
            <p className="hint">
              Rendered inside a sandboxed frame on the live page.
            </p>
          </div>
        </div>
      );
  }
}

// "✨ Help me write" — asks for a short brief, calls the assist endpoint, and
// drops the returned copy into the block. The suggestion is a starting point,
// not final copy, so we flag it for the author to review.
function AssistControl({
  onAiFill,
  aiSuggested,
}: {
  onAiFill: (text: string) => void;
  aiSuggested: boolean;
}) {
  const promptId = useId();
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function onSuggest() {
    setError('');
    if (!prompt.trim()) {
      setError('Add a short brief first, e.g. “welcome new volunteers”.');
      return;
    }
    setBusy(true);
    try {
      const { text } = await assistCopy(prompt.trim());
      onAiFill(text);
      setOpen(false);
      setPrompt('');
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'We couldn’t get a suggestion. Please try again.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="cms-assist">
      {!open ? (
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => setOpen(true)}
        >
          ✨ Help me write
        </button>
      ) : (
        <div className="cms-assist-panel">
          <div className="field">
            <label htmlFor={promptId} className="sr-only">
              What should this say?
            </label>
            <input
              id={promptId}
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="What should this say? e.g. “thank our volunteers”"
            />
          </div>
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <div className="cms-assist-actions">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => void onSuggest()}
              disabled={busy}
            >
              {busy ? 'Writing…' : 'Suggest copy'}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setOpen(false)}
              disabled={busy}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
      {aiSuggested && (
        <p className="cms-ai-hint muted">
          ✨ AI-suggested — edit before publishing.
        </p>
      )}
    </div>
  );
}
