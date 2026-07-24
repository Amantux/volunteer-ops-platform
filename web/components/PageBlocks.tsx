import type { PageBlock } from '@/lib/api';

// Shared renderer for CMS page blocks — used by BOTH the public server route
// (app/[slug]/page.tsx) and the admin editor's live preview, so what an author
// previews is exactly what visitors see.
//
// SECURITY (reviewed closely):
//   * paragraph.html and html.safe_html are SERVER-SANITIZED, so
//     dangerouslySetInnerHTML is acceptable for those two fields ONLY.
//   * embed.raw_html is UNSANITIZED and privileged — it is rendered
//     EXCLUSIVELY inside a sandboxed <iframe srcDoc> with NO allow-same-origin,
//     so contained scripts can never reach the parent DOM, cookies, or storage.
//     It never touches dangerouslySetInnerHTML.

function hasText(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function headingLevel(level: number): 1 | 2 | 3 | 4 {
  if (level <= 1) return 1;
  if (level >= 4) return 4;
  return level as 2 | 3;
}

function BlockView({ block }: { block: PageBlock }) {
  switch (block.type) {
    case 'heading': {
      if (!hasText(block.text)) return null;
      const Tag = `h${headingLevel(block.level)}` as 'h1' | 'h2' | 'h3' | 'h4';
      return <Tag>{block.text}</Tag>;
    }
    case 'paragraph':
      // Server-sanitized inline HTML — safe to render.
      return (
        <div
          className="pb-paragraph"
          dangerouslySetInnerHTML={{ __html: block.html }}
        />
      );
    case 'image':
      if (!hasText(block.url)) return null;
      // eslint-disable-next-line @next/next/no-img-element -- plain <img>: no
      // remote-image config, and sources are author-provided arbitrary URLs.
      return (
        <img
          className="pb-image"
          src={block.url}
          alt={block.alt ?? ''}
          loading="lazy"
        />
      );
    case 'button':
      if (!hasText(block.href)) return null;
      return (
        <p>
          <a className="btn btn-primary" href={block.href}>
            {hasText(block.label) ? block.label : block.href}
          </a>
        </p>
      );
    case 'divider':
      return <hr className="pb-divider" />;
    case 'html':
      // Server-sanitized privileged HTML — safe to render.
      return (
        <div
          className="pb-html"
          dangerouslySetInnerHTML={{ __html: block.safe_html }}
        />
      );
    case 'embed':
      // UNSANITIZED — sandboxed iframe, NO allow-same-origin. Never inlined.
      return (
        <iframe
          className="pb-embed"
          title="Embedded content"
          sandbox="allow-scripts allow-popups"
          srcDoc={block.raw_html}
          loading="lazy"
        />
      );
    default:
      return null;
  }
}

export default function PageBlocks({ blocks }: { blocks: PageBlock[] }) {
  return (
    <>
      {blocks.map((block, i) => (
        <BlockView key={i} block={block} />
      ))}
    </>
  );
}
