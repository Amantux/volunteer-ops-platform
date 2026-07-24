import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import FormRenderer from '@/components/FormRenderer';
import { getForm, type PublicForm } from '@/lib/api';

// Public dynamic form. Rendered per-request so the schema is always current.
export const dynamic = 'force-dynamic';

interface PageProps {
  params: { key: string };
}

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  try {
    const form = await getForm(params.key);
    if (!form) return { title: 'Form not found' };
    return { title: form.name, description: form.purpose };
  } catch {
    return { title: 'Form' };
  }
}

export default async function PublicFormPage({ params }: PageProps) {
  // A true 404 (unknown / unpublished key) renders not-found. A connectivity or
  // server failure degrades gracefully instead of a bare 500.
  let form: PublicForm | null;
  try {
    form = await getForm(params.key);
  } catch {
    return (
      <div className="container page">
        <h1>This form couldn&rsquo;t be loaded</h1>
        <div className="alert alert-danger" role="alert">
          <strong>Something went wrong on our end.</strong>
          <p>Please try again in a moment.</p>
        </div>
      </div>
    );
  }
  if (!form) notFound();

  return (
    <div className="container page auth-narrow">
      <h1>{form.name}</h1>
      {form.purpose && <p className="lede">{form.purpose}</p>}

      <div className="panel">
        <FormRenderer form={form} />
      </div>

      <p className="follow-up">
        Spotted something else that needs attention?{' '}
        <Link href="/forms/incident_report">Report an issue</Link>.
      </p>
    </div>
  );
}
