import type { Metadata } from 'next';
import KiosksClient from '@/components/KiosksClient';

export const metadata: Metadata = {
  title: 'Kiosks',
  description: 'Manage front-desk tablet kiosks — panels, check-in and tasks.',
};

export default function KiosksPage() {
  return <KiosksClient />;
}
