import type { Metadata } from 'next';
import OverviewClient from '@/components/OverviewClient';

export const metadata: Metadata = {
  title: 'Executive overview',
  description: 'Org-wide snapshot of volunteers, shifts, applications, and giving.',
};

export default function OverviewPage() {
  return <OverviewClient />;
}
