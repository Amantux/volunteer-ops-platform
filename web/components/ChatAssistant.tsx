'use client';

import { usePathname } from 'next/navigation';
import {
  Fragment,
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react';
import {
  type AgentAction,
  type AgentConfig,
  type ChatMessage,
  getAgentConfig,
  streamChat,
} from '@/lib/agent';
import { getToken } from '@/lib/auth';

// A rendered turn. Assistant turns accumulate tokens into `content` and collect
// tool runs into `actions` as they stream in.
interface Turn {
  role: 'user' | 'assistant';
  content: string;
  actions?: AgentAction[];
}

const SUGGESTIONS = [
  "What's on today?",
  'What shifts are open?',
  'How many volunteers are active?',
];

// Tiny, dependency-free, XSS-safe inline renderer. Builds React nodes (never
// dangerouslySetInnerHTML), so any HTML in the model output is inert text.
// Handles **bold**, `code`, and line breaks — everything else renders literally.
function renderInline(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /\*\*([^*]+)\*\*|`([^`]+)`/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    if (match[1] !== undefined) {
      nodes.push(<strong key={`${keyBase}-b${i}`}>{match[1]}</strong>);
    } else if (match[2] !== undefined) {
      nodes.push(<code key={`${keyBase}-c${i}`}>{match[2]}</code>);
    }
    last = pattern.lastIndex;
    i += 1;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function renderMarkdown(text: string): ReactNode {
  const lines = text.split('\n');
  return lines.map((line, idx) => (
    <Fragment key={idx}>
      {idx > 0 && <br />}
      {renderInline(line, `l${idx}`)}
    </Fragment>
  ));
}

export default function ChatAssistant() {
  const pathname = usePathname();
  const [hasToken, setHasToken] = useState(false);
  const [open, setOpen] = useState(false);
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  // True between "send" and the first streamed token — drives the typing dots.
  const [awaitingFirstToken, setAwaitingFirstToken] = useState(false);

  const bodyRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fabRef = useRef<HTMLButtonElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const titleId = useId();
  const logId = useId();

  // Re-evaluate the session token on every route change (login/logout don't
  // always full-reload), mirroring AuthNav's approach.
  useEffect(() => {
    setHasToken(!!getToken());
  }, [pathname]);

  // Refresh provider config whenever the panel opens (cheap; keeps the pill and
  // the input's enabled state honest without a reload).
  useEffect(() => {
    if (!open || !hasToken) return;
    let active = true;
    getAgentConfig()
      .then((c) => {
        if (active) setConfig(c);
      })
      .catch(() => {
        if (active) setConfig({ enabled: false, provider: '', model: null });
      });
    return () => {
      active = false;
    };
  }, [open, hasToken]);

  const scrollDown = useCallback(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  // Auto-scroll as the transcript grows / tokens stream in.
  useEffect(() => {
    scrollDown();
  }, [turns, busy, awaitingFirstToken, scrollDown]);

  // Focus management: move focus into the panel when it opens.
  useEffect(() => {
    if (open) {
      const t = window.setTimeout(() => inputRef.current?.focus(), 0);
      return () => window.clearTimeout(t);
    }
  }, [open]);

  const closePanel = useCallback(() => {
    abortRef.current?.abort();
    setOpen(false);
    // Return focus to the trigger for keyboard users.
    fabRef.current?.focus();
  }, []);

  const send = useCallback(
    async (text?: string) => {
      const content = (text ?? input).trim();
      if (!content || busy || !config?.enabled) return;

      setInput('');
      // Snapshot the full transcript (existing turns + this user turn) — this is
      // exactly what we resend to the stateless server.
      const outgoing: ChatMessage[] = [
        ...turns.map((t) => ({ role: t.role, content: t.content })),
        { role: 'user', content },
      ];
      // Seed the user turn and an empty assistant turn to stream into.
      setTurns((prev) => [
        ...prev,
        { role: 'user', content },
        { role: 'assistant', content: '', actions: [] },
      ]);
      setBusy(true);
      setAwaitingFirstToken(true);

      const controller = new AbortController();
      abortRef.current = controller;

      // Mutate ONLY the last (assistant) turn as events arrive.
      const patchLast = (fn: (t: Turn) => Turn) =>
        setTurns((prev) => {
          const next = [...prev];
          next[next.length - 1] = fn(next[next.length - 1]);
          return next;
        });

      try {
        await streamChat(outgoing, {
          signal: controller.signal,
          onToken: (tok) => {
            setAwaitingFirstToken(false);
            patchLast((t) => ({ ...t, content: t.content + tok }));
          },
          onAction: (action) => {
            patchLast((t) => ({
              ...t,
              actions: [...(t.actions ?? []), action],
            }));
          },
          onDone: () => {
            setAwaitingFirstToken(false);
          },
        });
      } catch (err) {
        if (controller.signal.aborted) return;
        const message =
          err instanceof Error ? err.message : 'Something went wrong.';
        patchLast((t) => ({
          ...t,
          content: t.content || `⚠️ ${message}`,
        }));
      } finally {
        setBusy(false);
        setAwaitingFirstToken(false);
        abortRef.current = null;
        window.setTimeout(() => inputRef.current?.focus(), 0);
      }
    },
    [input, busy, config, turns],
  );

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closePanel();
    }
  }

  // No session → the widget doesn't exist. (Also avoids a hydration mismatch:
  // hasToken starts false to match SSR, then flips in the effect above.)
  if (!hasToken) return null;

  const enabled = config?.enabled ?? false;
  const providerLabel = enabled ? config?.provider || 'ready' : 'not set up';

  return (
    <div className="chat-widget">
      <button
        ref={fabRef}
        type="button"
        className={`chat-fab${open ? ' is-open' : ''}`}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={open ? 'Close assistant' : 'Open assistant'}
        onClick={() => (open ? closePanel() : setOpen(true))}
      >
        <span aria-hidden="true">{open ? '✕' : '💬'}</span>
      </button>

      {open && (
        <div
          className="chat-panel"
          role="dialog"
          aria-modal="false"
          aria-labelledby={titleId}
          onKeyDown={(e) => {
            if (e.key === 'Escape') closePanel();
          }}
        >
          <div className="chat-head">
            <strong id={titleId}>Assistant</strong>
            <div className="chat-head-right">
              <span
                className={`pill ${enabled ? 'pill-open' : 'pill-neutral'} chat-status`}
              >
                {providerLabel}
              </span>
              <button
                type="button"
                className="chat-close"
                onClick={closePanel}
                aria-label="Close assistant"
              >
                <span aria-hidden="true">✕</span>
              </button>
            </div>
          </div>

          <div
            className="chat-body"
            ref={bodyRef}
            id={logId}
            role="log"
            aria-live="polite"
            aria-atomic="false"
            aria-label="Conversation"
          >
            {!enabled ? (
              <div className="chat-hello">
                <p className="muted">
                  The assistant isn’t set up yet. An administrator can connect a
                  provider under <strong>AI Assistant</strong> settings, then it
                  can answer questions about shifts, volunteers, and your day.
                </p>
              </div>
            ) : turns.length === 0 ? (
              <div className="chat-hello">
                <p className="muted">
                  Ask about your day — what’s scheduled, which shifts need
                  people, how volunteering is going.
                </p>
                <div className="chat-chips">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      type="button"
                      className="chat-chip"
                      onClick={() => void send(s)}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {turns.map((t, i) => (
              <div key={i} className={`chat-msg chat-msg-${t.role}`}>
                {(t.content || t.role === 'user') && (
                  <div className="chat-bubble">{renderMarkdown(t.content)}</div>
                )}
                {t.actions && t.actions.length > 0 && (
                  <div className="chat-acts">
                    {t.actions.map((a, j) => (
                      <div key={j} className={`chat-act chat-act-${a.kind || 'read'}`}>
                        <span className="chat-act-icon" aria-hidden="true">
                          {a.kind === 'draft' ? '✎' : a.kind === 'proposed' ? '⏳' : '🔍'}
                        </span>
                        <span className="chat-act-label">
                          {a.label || a.kind}
                          {a.kind === 'proposed' && ' — needs approval'}
                          {a.kind === 'draft' && ' — pending review'}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {awaitingFirstToken && (
              <div className="chat-msg chat-msg-assistant">
                <div className="chat-bubble chat-typing" aria-label="Assistant is typing">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}
          </div>

          <form
            className="chat-foot"
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <label className="sr-only" htmlFor={`${titleId}-input`}>
              Message the assistant
            </label>
            <textarea
              id={`${titleId}-input`}
              ref={inputRef}
              className="chat-input"
              rows={1}
              value={input}
              disabled={!enabled}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={
                enabled
                  ? 'Message the assistant…'
                  : 'Ask an admin to connect a provider'
              }
              aria-controls={logId}
            />
            <button
              type="submit"
              className="btn btn-primary chat-send"
              disabled={busy || !enabled || !input.trim()}
              aria-label="Send message"
            >
              <span aria-hidden="true">➤</span>
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
