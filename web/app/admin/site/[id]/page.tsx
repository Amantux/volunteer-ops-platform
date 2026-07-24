import type { Metadata } from 'next';
import SiteEditorClient from '@/components/SiteEditorClient';

export const metadata: Metadata = {
  title: 'Edit page',
  description: 'Build your page with blocks and publish it live.',
};

interface PageProps {
  params: { id: string };
}

export default function SiteEditorPage({ params }: PageProps) {
  return <SiteEditorClient id={params.id} />;
}
