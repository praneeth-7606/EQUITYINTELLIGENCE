import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { formatInr } from '../../lib/formatInr';

interface DividendTimelineEvent {
  symbol: string;
  ex_date: string;
  year: string;
  shares_held: number;
  amount_per_share: number;
  payout: number;
}

interface MissedDividendEvent {
  symbol: string;
  ex_date: string;
  amount_per_share: number;
  missed_payout: number;
  reason: string;
}

interface UpcomingDividendEvent {
  symbol: string;
  ex_date: string;
  amount_per_share: number;
  shares_held: number;
  projected_income: number;
  yield_pct: number;
  certainty: string;
}

interface DividendData {
  total_dividend_received: number;
  total_dividend_upcoming: number;
  total_dividend_missed: number;
  dividend_yield_percent: number;
  per_stock_dividend?: { symbol: string; received: number; missed: number }[];
  cumulative_dividend_timeline?: { date: string; cumulative: number }[];
  dividend_timeline?: DividendTimelineEvent[];
  missed_dividends?: MissedDividendEvent[];
  upcoming_dividends?: UpcomingDividendEvent[];
}

export default function DividendDashboard({ data }: { data: DividendData }) {
  const {
    total_dividend_received = 0,
    total_dividend_upcoming = 0,
    total_dividend_missed = 0,
    dividend_yield_percent = 0,
    per_stock_dividend = [],
    cumulative_dividend_timeline = [],
    dividend_timeline = [],
    upcoming_dividends = [],
  } = data;

  // Process data for annual dividends received: grouped by year & symbol
  const years = Array.from(new Set(dividend_timeline.map((d) => d.year))).sort();
  const activeSymbols = Array.from(new Set(dividend_timeline.map((d) => d.symbol)));

  const annualChartData = years.map((yr) => {
    const row: Record<string, any> = { year: yr };
    activeSymbols.forEach((sym) => {
      row[sym] = dividend_timeline
        .filter((d) => d.year === yr && d.symbol === sym)
        .reduce((sum, d) => sum + d.payout, 0);
    });
    return row;
  });

  // Unique colors for symbols in annual chart
  const SYMBOL_COLORS = ['#1BCA8A', '#D4A017', '#E84848', '#8899BB', '#E8C547', '#162A52', '#00A8FF'];

  const maxProjected = upcoming_dividends.reduce((max, d) => Math.max(max, d.projected_income), 0) || 1;

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="bg-surface border border-border rounded-xl p-4 flex flex-col justify-between min-h-[90px] relative overflow-hidden">
          <p className="text-muted text-[10px] font-bold tracking-wider uppercase">Total Received</p>
          <p className="font-display text-xl font-bold font-data text-gain">{formatInr(total_dividend_received)}</p>
          <span className="absolute right-3 top-3 text-xl opacity-20">💰</span>
        </div>
        <div className="bg-surface border border-border rounded-xl p-4 flex flex-col justify-between min-h-[90px] relative overflow-hidden">
          <p className="text-muted text-[10px] font-bold tracking-wider uppercase">Total Missed</p>
          <p className="font-display text-xl font-bold font-data text-loss">{formatInr(total_dividend_missed)}</p>
          <span className="absolute right-3 top-3 text-xl opacity-20">⚠️</span>
        </div>
        <div className="bg-surface border border-border rounded-xl p-4 flex flex-col justify-between min-h-[90px] relative overflow-hidden">
          <p className="text-muted text-[10px] font-bold tracking-wider uppercase">Yield on Cost</p>
          <p className="font-display text-xl font-bold font-data text-text">{dividend_yield_percent.toFixed(2)}%</p>
          <span className="absolute right-3 top-3 text-xl opacity-20">📊</span>
        </div>
        <div className="bg-surface border border-border rounded-xl p-4 flex flex-col justify-between min-h-[90px] relative overflow-hidden">
          <p className="text-muted text-[10px] font-bold tracking-wider uppercase">Upcoming Income</p>
          <p className="font-display text-xl font-bold font-data text-gold">{formatInr(total_dividend_upcoming)}</p>
          <span className="absolute right-3 top-3 text-xl opacity-20">📈</span>
        </div>
      </div>

      {/* Charts section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Annual dividends grouped bar */}
        <div className="bg-surface border border-border rounded-xl p-4">
          <p className="label mb-4">ANNUAL DIVIDENDS RECEIVED</p>
          {annualChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={annualChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1B3A6B" />
                <XAxis dataKey="year" tick={{ fill: '#8899BB', fontSize: 10 }} axisLine={{ stroke: '#1B3A6B' }} />
                <YAxis tick={{ fill: '#8899BB', fontSize: 10 }} axisLine={{ stroke: '#1B3A6B' }} />
                <Tooltip
                  contentStyle={{ background: '#0F2040', border: '1px solid #1B3A6B', color: '#E8EDF5' }}
                  formatter={(val: any) => formatInr(Number(val))}
                />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                {activeSymbols.map((sym, index) => (
                  <Bar
                    key={sym}
                    dataKey={sym}
                    fill={SYMBOL_COLORS[index % SYMBOL_COLORS.length]}
                    stackId="a"
                    radius={[2, 2, 0, 0]}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[280px] flex items-center justify-center text-muted text-sm">No historical payouts.</div>
          )}
        </div>

        {/* Received vs missed per stock */}
        <div className="bg-surface border border-border rounded-xl p-4">
          <p className="label mb-4">RECEIVED VS MISSED PER STOCK</p>
          {per_stock_dividend.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={per_stock_dividend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1B3A6B" />
                <XAxis dataKey="symbol" tick={{ fill: '#8899BB', fontSize: 10 }} axisLine={{ stroke: '#1B3A6B' }} />
                <YAxis tick={{ fill: '#8899BB', fontSize: 10 }} axisLine={{ stroke: '#1B3A6B' }} />
                <Tooltip
                  contentStyle={{ background: '#0F2040', border: '1px solid #1B3A6B', color: '#E8EDF5' }}
                  formatter={(val: any) => formatInr(Number(val))}
                />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                <Bar dataKey="received" name="Received" fill="#1BCA8A" radius={[4, 4, 0, 0]} />
                <Bar dataKey="missed" name="Missed (Exited Early)" fill="#E84848" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[280px] flex items-center justify-center text-muted text-sm">No comparison data.</div>
          )}
        </div>

        {/* Dividend Yield Velocity Timeline */}
        <div className="bg-surface border border-border rounded-xl p-4 lg:col-span-2">
          <p className="label mb-4">CUMULATIVE RECEIVED INCOME TIMELINE</p>
          {cumulative_dividend_timeline.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={cumulative_dividend_timeline}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1B3A6B" />
                <XAxis dataKey="date" tick={{ fill: '#8899BB', fontSize: 10 }} axisLine={{ stroke: '#1B3A6B' }} />
                <YAxis tick={{ fill: '#8899BB', fontSize: 10 }} axisLine={{ stroke: '#1B3A6B' }} />
                <Tooltip
                  contentStyle={{ background: '#0F2040', border: '1px solid #1B3A6B', color: '#E8EDF5' }}
                  formatter={(val: any) => formatInr(Number(val))}
                />
                <Line type="monotone" dataKey="cumulative" stroke="#D4A017" strokeWidth={2} activeDot={{ r: 6 }} name="Cumulative" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-muted text-sm">No timeline data.</div>
          )}
        </div>
      </div>

      {/* Upcoming Dividends Section */}
      <div className="bg-surface border border-border rounded-xl p-4">
        <p className="label mb-3">UPCOMING DIVIDENDS</p>
        {upcoming_dividends.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-border text-muted uppercase tracking-wider text-[10px]">
                  <th className="py-2.5 px-3">Stock</th>
                  <th className="py-2.5 px-3">Ex-Date</th>
                  <th className="py-2.5 px-3 text-right">Per Share</th>
                  <th className="py-2.5 px-3 text-right">Shares Held</th>
                  <th className="py-2.5 px-3 text-right">Projected Income</th>
                  <th className="py-2.5 px-3">Certainty</th>
                  <th className="py-2.5 px-3 min-w-[120px]">Income Relative Size</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {upcoming_dividends.map((row, i) => {
                  const pct = Math.min((row.projected_income / maxProjected) * 100, 100);
                  return (
                    <tr key={i} className="hover:bg-raised/35 transition-colors">
                      <td className="py-2.5 px-3 font-semibold text-text">{row.symbol}</td>
                      <td className="py-2.5 px-3 text-muted font-mono">{row.ex_date}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-text">₹{row.amount_per_share.toFixed(2)}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-text">{row.shares_held}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-gold font-semibold">₹{row.projected_income.toFixed(2)}</td>
                      <td className="py-2.5 px-3">
                        <span className={`px-2 py-0.5 rounded text-[9px] uppercase font-bold tracking-wider 
                          ${row.certainty === 'announced' ? 'bg-gain/20 text-gain' : 'bg-gold/20 text-gold'}`}
                        >
                          {row.certainty}
                        </span>
                      </td>
                      <td className="py-2.5 px-3">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 bg-canvas h-1.5 rounded-full overflow-hidden border border-border/40">
                            <div className="bg-gain h-full rounded-full" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-[10px] text-muted font-mono w-6 text-right">{pct.toFixed(0)}%</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-8 text-center text-muted text-xs">No upcoming dividend payouts announced for your holdings.</div>
        )}
      </div>
    </div>
  );
}
