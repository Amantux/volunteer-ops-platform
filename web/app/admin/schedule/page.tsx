import type { Metadata } from 'next';
import ScheduleAdminClient from '@/components/ScheduleAdminClient';

export const metadata: Metadata = {
  title: 'Schedule',
  description: 'Create signup sheets and generate recurring volunteer slots.',
};

export default function ScheduleAdminPage() {
  return <ScheduleAdminClient />;
}
