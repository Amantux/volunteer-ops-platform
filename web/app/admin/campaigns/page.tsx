import type { Metadata } from 'next';
import CampaignsClient from '@/components/CampaignsClient';

export const metadata: Metadata = {
  title: 'Campaigns',
  description: 'Manage fundraising campaigns and their public donate pages.',
};

export default function CampaignsPage() {
  return <CampaignsClient />;
}
