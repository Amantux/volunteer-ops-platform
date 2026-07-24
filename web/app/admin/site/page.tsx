import type { Metadata } from 'next';
import SiteAdminClient from '@/components/SiteAdminClient';

export const metadata: Metadata = {
  title: 'Site pages',
  description: 'Build and publish pages for your public site.',
};

export default function SiteAdminPage() {
  return <SiteAdminClient />;
}
