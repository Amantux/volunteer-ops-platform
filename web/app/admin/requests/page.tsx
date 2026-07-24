import type { Metadata } from 'next';
import RequestsClient from '@/components/RequestsClient';

export const metadata: Metadata = {
  title: 'Requests',
  description: 'Review incident reports and move them through their workflow.',
};

export default function RequestsPage() {
  return <RequestsClient />;
}
