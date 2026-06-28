import { useAppStore } from '../../store/appStore';
import StreamingKPICard from '../shared/StreamingKPICard';
import PnLBarChart from './PnLBarChart';
import ChargesDonut from './ChargesDonut';
import OpenPositionsTable from './OpenPositionsTable';
import RealisedTradesTable from './RealisedTradesTable';
import StockAnalysisDashboard from './StockAnalysisDashboard';
import DividendDashboard from './DividendDashboard';

export default function DashboardView() {
  const { kpis, isStreaming, messages } = useAppStore();

  const lastAgentMsg = [...messages].reverse().find((m) => m.role === 'agent' && m.structuredData);
  const isStockAnalysis = lastAgentMsg?.agentUsed === 'stock_analysis_agent' || (lastAgentMsg?.structuredData && 'fundamentals' in lastAgentMsg.structuredData);
  const isDividend = lastAgentMsg?.agentUsed === 'dividend_agent';

  const hasData = kpis.length > 0 || messages.some((m) => m.role === 'agent' && m.content);

  if (!hasData) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-center space-y-3 max-w-sm">
          <div className="text-4xl">📊</div>
          <h2 className="text-text text-lg font-semibold">Dashboard</h2>
          <p className="text-muted text-sm leading-relaxed">
            Ask a question in the chat to populate your dashboard.
          </p>
        </div>
      </div>
    );
  }

  if (isStockAnalysis && lastAgentMsg?.structuredData) {
    return (
      <div className="flex-1 overflow-y-auto p-5 space-y-6">
        {/* KPI Row */}
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          {kpis.map((kpi, i) => (
            <StreamingKPICard
              key={i}
              label={kpi.label}
              value={kpi.value}
              type={kpi.type}
              status={isStreaming ? 'streaming' : 'done'}
            />
          ))}
        </div>
        <StockAnalysisDashboard data={lastAgentMsg.structuredData as any} />
      </div>
    );
  }

  if (isDividend && lastAgentMsg?.structuredData) {
    return (
      <div className="flex-1 overflow-y-auto p-5 space-y-6">
        <DividendDashboard data={lastAgentMsg.structuredData as any} />
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-6">
      {/* KPI Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {kpis.length > 0 ? (
          kpis.map((kpi, i) => (
            <StreamingKPICard
              key={i}
              label={kpi.label}
              value={kpi.value}
              type={kpi.type}
              status={isStreaming ? 'streaming' : 'done'}
            />
          ))
        ) : (
          <>
            <StreamingKPICard label="Total Invested" value="—" type="neutral" status="loading" />
            <StreamingKPICard label="Realised P&L" value="—" type="neutral" status="loading" />
            <StreamingKPICard label="Current Value" value="—" type="neutral" status="loading" />
            <StreamingKPICard label="Total Charges" value="—" type="neutral" status="loading" />
          </>
        )}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-3">
          <PnLBarChart />
        </div>
        <div className="lg:col-span-2">
          <ChargesDonut />
        </div>
      </div>

      {/* Tables */}
      <OpenPositionsTable />
      <RealisedTradesTable />
    </div>
  );
}
