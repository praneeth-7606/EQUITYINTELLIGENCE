interface KPICardProps {
  label: string;
  value: string;
  type: 'gain' | 'loss' | 'neutral';
  status: 'loading' | 'streaming' | 'done';
}

export default function StreamingKPICard({ label, value, type, status }: KPICardProps) {
  const colorClass =
    type === 'gain' ? 'text-gain' :
    type === 'loss' ? 'text-loss' :
    'text-text';

  return (
    <div className="bg-surface border border-border rounded-xl p-4 flex flex-col gap-2 min-w-0">
      <span className="label">{label}</span>
      {status === 'loading' ? (
        <div className="shimmer h-8 w-28 rounded" />
      ) : (
        <span
          className={`kpi-value ${colorClass} ${status === 'streaming' ? 'streaming-cursor' : ''}`}
          aria-live="polite"
        >
          {value}
        </span>
      )}
    </div>
  );
}
