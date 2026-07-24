import type { Metadata } from 'next';
import SocialAdminClient from '@/components/SocialAdminClient';

export const metadata: Metadata = {
  title: 'Social posts',
  description: 'Draft, approve and publish posts to your social channels.',
};

export default function SocialAdminPage() {
  return <SocialAdminClient />;
}
