import type { Metadata } from 'next';
import AssistantSettingsClient from '@/components/AssistantSettingsClient';

export const metadata: Metadata = {
  title: 'AI Assistant',
  description: 'Connect a language model to power the chat assistant.',
};

export default function AssistantSettingsPage() {
  return <AssistantSettingsClient />;
}
