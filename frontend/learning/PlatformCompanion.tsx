import { useMemo } from 'react';
import { Companion } from '../platform/companion/Companion';
import type { CompanionAction, CompanionContext, CompanionTransport } from '../platform/companion/types';
import type { LearningApi } from './api';
import type { Route } from './types';

export function PlatformCompanion({ api, identityKey, context, navigate, canLeave, learnerMode, onDirty, disabled }: {
  api: LearningApi; identityKey: string; context: CompanionContext; navigate: (route: Route) => Promise<boolean>;
  canLeave: () => Promise<boolean>; learnerMode: boolean; onDirty?: (dirty: boolean) => void; disabled?: boolean;
}) {
  const transport = useMemo<CompanionTransport>(() => ({
    open: body => api.platform('/companion/sessions', 'POST', body),
    read: id => api.platform(`/companion/sessions/${encodeURIComponent(id)}`),
    send: (id, body) => api.platform(`/companion/sessions/${encodeURIComponent(id)}/messages`, 'POST', body),
    readMessage: (id, messageId) => api.platform(`/companion/sessions/${encodeURIComponent(id)}/messages/${encodeURIComponent(messageId)}`),
  }), [api]);
  async function action(value: CompanionAction) {
    if (value.kind === 'open_course_hall') await navigate('#/learn/courses');
    else if (value.kind === 'open_hackathon_hall') await navigate('#/hackathon');
    else if (value.kind === 'open_portfolio') await navigate('#/portfolio');
    else if (value.kind === 'open_competition_team') {
      if (learnerMode) await navigate('#/hackathon');
      else if (await canLeave()) location.assign('/#/work');
    }
  }
  return <Companion identityKey={identityKey} context={context} transport={transport} presentation="floating" onAction={action} onDirty={onDirty} disabled={disabled} />;
}
