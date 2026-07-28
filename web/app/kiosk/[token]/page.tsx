import type { Metadata } from 'next';
import KioskDisplay from '@/components/KioskDisplay';

// Public signage: the token in the URL is the only capability. No indexing.
export const metadata: Metadata = {
  title: 'Kiosk',
  robots: { index: false, follow: false },
};

export default function KioskDisplayPage({
  params,
}: {
  params: { token: string };
}) {
  return <KioskDisplay token={params.token} />;
}
