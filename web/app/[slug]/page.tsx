import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import PageBlocks from '@/components/PageBlocks';
import { getPublicPage, type PublicPage } from '@/lib/api';

// Dynamic catch-all for CMS pages. Next resolves static routes (/, /dashboard,
// /trainings, …) before this single-segment dynamic route, so it only handles
// slugs that have no static page of their own.
export const dynamic = 'force-dynamic';

interface PageProps {
  params: { slug: string };
}

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  try {
    const page = await getPublicPage(params.slug);
    if (!page) return { title: 'Page not found' };
    return { title: page.title };
  } catch {
    return { title: 'Page' };
  }
}

export default async function CmsPage({ params }: PageProps) {
  // A true 404 (not published / unknown slug) renders not-found. A connectivity
  // or server failure degrades gracefully instead of a bare 500.
  let page: PublicPage | null;
  try {
    page = await getPublicPage(params.slug);
  } catch {
    return (
      <div className="container page">
        <h1>This page couldn&rsquo;t be loaded</h1>
        <div className="alert alert-danger" role="alert">
          <strong>Something went wrong on our end.</strong>
          <p>Please try again in a moment.</p>
        </div>
      </div>
    );
  }
  if (!page) notFound();

  return (
    <div className="container page">
      {/* Page CSS is server-sanitized and already scoped to #page-{scope_id}. */}
      {page.css ? (
        <style dangerouslySetInnerHTML={{ __html: page.css }} />
      ) : null}
      <div id={`page-${page.scope_id}`} className="page-content">
        <PageBlocks blocks={page.blocks} />
      </div>
    </div>
  );
}
