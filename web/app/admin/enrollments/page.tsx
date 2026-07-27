import type { Metadata } from 'next';
import EnrollmentsClient from '@/components/EnrollmentsClient';

export const metadata: Metadata = {
  title: 'Enrollments',
  description: 'Manage long-term volunteer program enrollments.',
};

export default function EnrollmentsPage() {
  return <EnrollmentsClient />;
}
