import type { Metadata } from 'next';
import DashboardClient from '@/components/DashboardClient';

export const metadata: Metadata = {
  title: 'Dashboard',
  description: 'Manage your volunteer shifts and rosters.',
};

export default function DashboardPage() {
  return <DashboardClient />;
}
