import { getAgentLabel } from '../../lib/agentLabels';

interface AgentBadgeProps {
  agentUsed: string;
  confidence?: string;
  routed?: boolean;
}

export default function AgentBadge({ agentUsed, confidence = 'high', routed = false }: AgentBadgeProps) {
  const dotColor =
    confidence === 'high' ? 'bg-gain' :
    confidence === 'medium' ? 'bg-gold' :
    'bg-loss';

  return (
    <div className="inline-flex items-center gap-1.5 bg-surface border border-border rounded-full px-2.5 py-1 text-[11px]">
      <span className="text-muted">🤖</span>
      {routed && <span className="text-muted">Routed →</span>}
      <span className="text-text font-medium">{getAgentLabel(agentUsed)}</span>
      <span
        className={`w-1.5 h-1.5 rounded-full ${dotColor}`}
        aria-label={`Confidence: ${confidence}`}
      />
    </div>
  );
}
