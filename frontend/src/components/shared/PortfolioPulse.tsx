import { useAppStore } from '../../store/appStore';

interface KPIProps {
  label: string;
  value: string;
  type: 'gain' | 'loss' | 'neutral';
  status: 'loading' | 'streaming' | 'done';
}

function StreamingKPICard({ label, value, type, status }: KPIProps) {
  const colorClass = type === 'gain' ? 'text-gain' : type === 'loss' ? 'text-loss' : 'text-text';

  if (status === 'loading') {
    return (
      <div className="flex flex-col gap-1.5">
        <span className="label">{label}</span>
        <div className="shimmer h-7 w-24 rounded" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="label">{label}</span>
      <span className={`font-display text-[22px] leading-none tracking-tight ${colorClass}`}
            aria-live="polite">
        {value}
        {status === 'streaming' && <span className="streaming-cursor" />}
      </span>
    </div>
  );
}

export default function PortfolioPulse() {
  const { isStreaming, kpis } = useAppStore();

  const invested = kpis.find((k) => k.label.toLowerCase().includes('invested'));
  const pnl = kpis.find((k) => k.label.toLowerCase().includes('p&l') || k.label.toLowerCase().includes('realised'));
  const openCost = kpis.find((k) => k.label.toLowerCase().includes('current') || k.label.toLowerCase().includes('open'));

  return (
    <div className="border-t border-border pt-3 mt-3">
      <div className={`pulse-bar mb-3 rounded-full ${isStreaming ? 'active' : ''}`} />

      <p className="label mb-3 flex items-center gap-2">
        PORTFOLIO PULSE
        {isStreaming && <span className="inline-block w-1.5 h-1.5 rounded-full bg-gold animate-pulse" />}
      </p>

      <div className="space-y-3">
        <StreamingKPICard
          label="INVESTED"
          value={invested?.value || '—'}
          type="neutral"
          status={isStreaming ? 'streaming' : invested ? 'done' : 'loading'}
        />
        <StreamingKPICard
          label="REALISED P&L"
          value={pnl?.value || '—'}
          type={pnl?.type || 'neutral'}
          status={isStreaming ? 'streaming' : pnl ? 'done' : 'loading'}
        />
        <StreamingKPICard
          label="CURRENT VALUE"
          value={openCost?.value || '—'}
          type="neutral"
          status={isStreaming ? 'streaming' : openCost ? 'done' : 'loading'}
        />
      </div>
    </div>
  );
}
