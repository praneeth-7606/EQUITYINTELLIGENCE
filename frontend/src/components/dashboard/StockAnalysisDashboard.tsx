import { useState } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';

interface Fundamental {
  market_cap?: number;
  pe_ratio?: number;
  forward_pe?: number;
  pb_ratio?: number;
  eps?: number;
  dividend_yield?: number;
  book_value?: number;
  revenue?: number;
  net_profit?: number;
  operating_margin_pct?: number;
  roe_pct?: number;
  roce_pct?: number;
  debt?: number;
  free_cash_flow?: number;
  enterprise_value?: number;
  shares_outstanding?: number;
}

interface PriceMetrics {
  year_open: number;
  year_close: number;
  high: number;
  low: number;
  annual_return_pct: number;
  avg_volume: number;
  volatility_pct: number;
  max_drawdown_pct: number;
}

interface MonthlyMetric {
  month: string;
  open: number;
  close: number;
  high: number;
  low: number;
  return_pct: number;
}

interface ChartRow {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface CorporateAction {
  date: string;
  amount?: number;
  ratio?: number;
  description: string;
}

interface YearData {
  price_metrics: PriceMetrics;
  monthly_metrics: MonthlyMetric[];
  ohlcv_chart_data: ChartRow[];
  corporate_actions: {
    dividends: CorporateAction[];
    splits_and_bonuses: CorporateAction[];
  };
  narrative_summary?: string;
  observations?: string[];
}

interface YearlyTotal {
  year: string;
  count: number;
  total_per_share: number;
  events: { date: string; amount: number; description: string }[];
}

interface FullDividendData {
  ticker: string;
  company_name: string;
  mode: 'full_dividend_history';
  total_cumulative_dividend_per_share: number;
  current_dividend_yield_pct: number;
  current_price: number;
  years_count: number;
  dividends_count: number;
  yearly_totals: YearlyTotal[];
  all_dividends: { date: string; amount: number; description: string }[];
  fundamentals: Fundamental;
}

interface StructuredData {
  ticker: string;
  company_name: string;
  fundamentals: Fundamental;
  years?: Record<string, YearData>;
  mode?: string;
  // full dividend history fields
  total_cumulative_dividend_per_share?: number;
  current_dividend_yield_pct?: number;
  current_price?: number;
  years_count?: number;
  dividends_count?: number;
  yearly_totals?: YearlyTotal[];
  all_dividends?: { date: string; amount: number; description: string }[];
}

interface Props {
  data: StructuredData;
}

// ── Full Dividend History View ──────────────────────────────────────────────
function DividendHistoryView({ data }: { data: FullDividendData }) {
  const {
    company_name,
    ticker,
    total_cumulative_dividend_per_share = 0,
    current_dividend_yield_pct = 0,
    yearly_totals = [],
    all_dividends = []
  } = data;

  const chartData = (yearly_totals || []).map(row => ({
    year: row.year,
    total: row.total_per_share || 0,
    count: row.count || 0
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-surface border border-border rounded-xl p-5">
        <span className="text-[10px] font-bold text-gold tracking-wider uppercase bg-gold/10 px-2.5 py-1 rounded-full">
          Complete Dividend History
        </span>
        <h2 className="text-2xl text-text font-display font-bold mt-2">{company_name}</h2>
        <p className="text-muted text-xs font-data mt-1">{ticker}</p>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-surface border border-border rounded-xl p-4 space-y-1">
          <p className="text-[10px] text-muted font-bold tracking-wider uppercase">Total Dividends Per Share</p>
          <p className="text-xl font-bold font-data text-gold">₹{total_cumulative_dividend_per_share.toFixed(2)}</p>
        </div>
        <div className="bg-surface border border-border rounded-xl p-4 space-y-1">
          <p className="text-[10px] text-muted font-bold tracking-wider uppercase">Current Yield</p>
          <p className="text-xl font-bold font-data text-gain">{current_dividend_yield_pct.toFixed(2)}%</p>
        </div>
        <div className="bg-surface border border-border rounded-xl p-4 space-y-1">
          <p className="text-[10px] text-muted font-bold tracking-wider uppercase">Total Payments</p>
          <p className="text-xl font-bold font-data text-text">{all_dividends.length}</p>
        </div>
        <div className="bg-surface border border-border rounded-xl p-4 space-y-1">
          <p className="text-[10px] text-muted font-bold tracking-wider uppercase">Years Active</p>
          <p className="text-xl font-bold font-data text-text">{yearly_totals.length}</p>
        </div>
      </div>

      {/* Year-wise Bar Chart */}
      <div className="bg-surface border border-border rounded-xl p-5">
        <p className="label mb-4">ANNUAL DIVIDEND PAYOUT (₹/SHARE)</p>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1B3A6B" />
            <XAxis dataKey="year" tick={{ fill: '#8899BB', fontSize: 10, fontFamily: 'Inter' }} axisLine={{ stroke: '#1B3A6B' }} tickLine={false} />
            <YAxis tick={{ fill: '#8899BB', fontSize: 10, fontFamily: 'JetBrains Mono' }} axisLine={{ stroke: '#1B3A6B' }} tickLine={false} />
            <Tooltip
              contentStyle={{ background: '#0F2040', border: '1px solid #1B3A6B', borderRadius: '8px', fontSize: '12px', fontFamily: 'JetBrains Mono', color: '#E8EDF5' }}
              formatter={(val: any) => [`₹${Number(val || 0).toFixed(2)}`, 'Total/Share']}
            />
            <Bar dataKey="total" fill="#D4A017" radius={[4, 4, 0, 0]} name="Total/Share" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Yearly Summary Table + All Events */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Year-wise summary */}
        <div className="bg-surface border border-border rounded-xl p-5">
          <p className="label mb-4">YEAR-WISE SUMMARY</p>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-border text-[10px] text-muted font-bold uppercase tracking-wider">
                  <th className="py-2.5">Year</th>
                  <th className="py-2.5 text-right">Payments</th>
                  <th className="py-2.5 text-right">Total/Share</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40 text-sm font-data">
                {[...yearly_totals].reverse().map((row, idx) => (
                  <tr key={idx} className="hover:bg-canvas/20">
                    <td className="py-2 font-semibold text-text">{row.year}</td>
                    <td className="py-2 text-right text-muted">{row.count}</td>
                    <td className="py-2 text-right text-gold font-semibold">₹{row.total_per_share.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* All dividend events */}
        <div className="bg-surface border border-border rounded-xl p-5">
          <p className="label mb-4">ALL DIVIDEND EVENTS ({all_dividends.length})</p>
          <div className="overflow-y-auto max-h-[400px] space-y-1.5 pr-1">
            {[...all_dividends].reverse().map((div, i) => (
              <div key={i} className="flex justify-between items-center bg-canvas/30 border border-border/40 px-3 py-2 rounded-lg text-xs">
                <span className="text-muted font-data">{div.date}</span>
                <span className="text-gold font-semibold font-data">₹{div.amount.toFixed(4)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Standard Stock Analysis View ─────────────────────────────────────────────
export default function StockAnalysisDashboard({ data }: Props) {
  // Full dividend history mode
  if (data.mode === 'full_dividend_history' && data.yearly_totals) {
    return <DividendHistoryView data={data as unknown as FullDividendData} />;
  }

  const { ticker, company_name, fundamentals, years } = data;
  const yearList = Object.keys(years || {}).sort();
  const [selectedYear, setSelectedYear] = useState<string>(yearList[yearList.length - 1] || '');

  const activeYearData = years?.[selectedYear];

  if (!activeYearData) {
    return (
      <div className="bg-surface border border-border rounded-xl p-8 flex items-center justify-center h-[300px]">
        <p className="text-muted text-sm">No analysis data found for the selected years.</p>
      </div>
    );
  }

  const { price_metrics, monthly_metrics, ohlcv_chart_data, corporate_actions, narrative_summary, observations } = activeYearData;

  const formatLargeNum = (num: number | undefined) => {
    if (num == null) return '—';
    if (num >= 1e12) return `₹${(num / 1e12).toFixed(2)}T`;
    if (num >= 1e7) return `₹${(num / 1e7).toFixed(1)}Cr`;
    return `₹${num.toLocaleString('en-IN')}`;
  };

  return (
    <div className="space-y-6">
      {/* Header Info */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-surface border border-border rounded-xl p-5">
        <div>
          <span className="text-[10px] font-bold text-gold tracking-wider uppercase bg-gold/10 px-2.5 py-1 rounded-full">
            Single Stock Analysis
          </span>
          <h2 className="text-2xl text-text font-display font-bold mt-2">{company_name}</h2>
          <p className="text-muted text-xs font-data mt-1">{ticker}</p>
        </div>

        {yearList.length > 1 && (
          <div className="flex gap-1.5 bg-canvas/60 border border-border p-1 rounded-xl self-start md:self-auto">
            {yearList.map((yr) => (
              <button
                key={yr}
                onClick={() => setSelectedYear(yr)}
                className={`px-4 py-1.5 rounded-lg text-xs font-semibold tracking-wide transition-all
                  ${selectedYear === yr
                    ? 'bg-gold text-canvas shadow-lg shadow-gold/15'
                    : 'text-muted hover:text-text'
                  }`}
              >
                {yr}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Fundamentals Grid */}
      <div className="bg-surface border border-border rounded-xl p-5">
        <p className="label mb-4">COMPANY FUNDAMENTALS</p>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <div className="space-y-1">
            <p className="text-[10px] text-muted font-bold tracking-wider uppercase">Market Cap</p>
            <p className="text-base text-text font-data font-semibold">{formatLargeNum(fundamentals.market_cap)}</p>
          </div>
          <div className="space-y-1">
            <p className="text-[10px] text-muted font-bold tracking-wider uppercase">P/E Ratio</p>
            <p className="text-base text-text font-data font-semibold">{fundamentals.pe_ratio != null ? `${fundamentals.pe_ratio.toFixed(1)}x` : '—'}</p>
          </div>
          <div className="space-y-1">
            <p className="text-[10px] text-muted font-bold tracking-wider uppercase">P/B Ratio</p>
            <p className="text-base text-text font-data font-semibold">{fundamentals.pb_ratio != null ? `${fundamentals.pb_ratio.toFixed(2)}x` : '—'}</p>
          </div>
          <div className="space-y-1">
            <p className="text-[10px] text-muted font-bold tracking-wider uppercase">EPS</p>
            <p className="text-base text-text font-data font-semibold">{fundamentals.eps != null ? `₹${fundamentals.eps.toFixed(1)}` : '—'}</p>
          </div>
          <div className="space-y-1">
            <p className="text-[10px] text-muted font-bold tracking-wider uppercase">Div Yield</p>
            <p className="text-base text-text font-data font-semibold">{fundamentals.dividend_yield != null ? `${fundamentals.dividend_yield.toFixed(2)}%` : '—'}</p>
          </div>
          <div className="space-y-1">
            <p className="text-[10px] text-muted font-bold tracking-wider uppercase">Book Value</p>
            <p className="text-base text-text font-data font-semibold">{fundamentals.book_value != null ? `₹${fundamentals.book_value.toFixed(1)}` : '—'}</p>
          </div>
          <div className="space-y-1">
            <p className="text-[10px] text-muted font-bold tracking-wider uppercase">Revenue</p>
            <p className="text-base text-text font-data font-semibold">{formatLargeNum(fundamentals.revenue)}</p>
          </div>
          <div className="space-y-1">
            <p className="text-[10px] text-muted font-bold tracking-wider uppercase">Net Profit</p>
            <p className="text-base text-text font-data font-semibold">{formatLargeNum(fundamentals.net_profit)}</p>
          </div>
          <div className="space-y-1">
            <p className="text-[10px] text-muted font-bold tracking-wider uppercase">Operating Margin</p>
            <p className="text-base text-text font-data font-semibold">{fundamentals.operating_margin_pct != null ? `${fundamentals.operating_margin_pct.toFixed(1)}%` : '—'}</p>
          </div>
          <div className="space-y-1">
            <p className="text-[10px] text-muted font-bold tracking-wider uppercase">ROE / ROCE</p>
            <p className="text-base text-text font-data font-semibold">
              {fundamentals.roe_pct != null ? `${fundamentals.roe_pct.toFixed(1)}%` : '—'} / {fundamentals.roce_pct != null ? `${fundamentals.roce_pct.toFixed(1)}%` : '—'}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-[10px] text-muted font-bold tracking-wider uppercase">Total Debt</p>
            <p className="text-base text-text font-data font-semibold">{formatLargeNum(fundamentals.debt)}</p>
          </div>
          <div className="space-y-1">
            <p className="text-[10px] text-muted font-bold tracking-wider uppercase">Free Cash Flow</p>
            <p className="text-base text-text font-data font-semibold">{formatLargeNum(fundamentals.free_cash_flow)}</p>
          </div>
        </div>
      </div>

      {/* Year Pricing Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-surface border border-border rounded-xl p-4 space-y-1">
          <p className="text-[10px] text-muted font-bold tracking-wider uppercase">Annual Return</p>
          <p className={`text-xl font-bold font-data ${price_metrics.annual_return_pct >= 0 ? 'text-gain' : 'text-loss'}`}>
            {price_metrics.annual_return_pct >= 0 ? '+' : ''}{price_metrics.annual_return_pct.toFixed(2)}%
          </p>
        </div>
        <div className="bg-surface border border-border rounded-xl p-4 space-y-1">
          <p className="text-[10px] text-muted font-bold tracking-wider uppercase">Price Range (High / Low)</p>
          <p className="text-xl text-text font-bold font-data">
            ₹{price_metrics.high} <span className="text-muted text-sm font-medium">/</span> ₹{price_metrics.low}
          </p>
        </div>
        <div className="bg-surface border border-border rounded-xl p-4 space-y-1">
          <p className="text-[10px] text-muted font-bold tracking-wider uppercase">Annual Volatility</p>
          <p className="text-xl text-text font-bold font-data">{price_metrics.volatility_pct.toFixed(2)}%</p>
        </div>
        <div className="bg-surface border border-border rounded-xl p-4 space-y-1">
          <p className="text-[10px] text-muted font-bold tracking-wider uppercase">Max Drawdown</p>
          <p className="text-xl text-loss font-bold font-data">{price_metrics.max_drawdown_pct.toFixed(2)}%</p>
        </div>
      </div>

      {/* Price Chart */}
      <div className="bg-surface border border-border rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <p className="label">{selectedYear} PRICE MOVEMENT</p>
          <span className="text-xs text-muted font-data">
            Avg Vol: {(price_metrics.avg_volume / 1e5).toFixed(1)}L per day
          </span>
        </div>
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart data={ohlcv_chart_data} margin={{ top: 10, right: 10, left: -20, bottom: 5 }}>
            <defs>
              <linearGradient id="colorClose" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#D4A017" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#D4A017" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1B3A6B" />
            <XAxis dataKey="date" tick={{ fill: '#8899BB', fontSize: 10, fontFamily: 'Inter' }} axisLine={{ stroke: '#1B3A6B' }} tickLine={false} minTickGap={40} />
            <YAxis domain={['auto', 'auto']} tick={{ fill: '#8899BB', fontSize: 10, fontFamily: 'JetBrains Mono' }} axisLine={{ stroke: '#1B3A6B' }} tickLine={false} />
            <Tooltip contentStyle={{ background: '#0F2040', border: '1px solid #1B3A6B', borderRadius: '8px', fontSize: '12px', fontFamily: 'JetBrains Mono', color: '#E8EDF5' }} />
            <Area type="monotone" dataKey="close" stroke="#D4A017" strokeWidth={2.5} fillOpacity={1} fill="url(#colorClose)" name="Close" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Monthly Returns + AI Insights */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-surface border border-border rounded-xl p-5 space-y-4">
          <p className="label">MONTHLY PERFORMANCE BREAKDOWN</p>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-border text-[10px] text-muted font-bold uppercase tracking-wider">
                  <th className="py-2.5">Month</th>
                  <th className="py-2.5 text-right">Open</th>
                  <th className="py-2.5 text-right">Close</th>
                  <th className="py-2.5 text-right">High / Low</th>
                  <th className="py-2.5 text-right">Return</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40 text-sm font-data">
                {monthly_metrics.map((m, idx) => (
                  <tr key={idx} className="hover:bg-canvas/20">
                    <td className="py-2 font-medium text-text">{m.month}</td>
                    <td className="py-2 text-right">₹{m.open}</td>
                    <td className="py-2 text-right">₹{m.close}</td>
                    <td className="py-2 text-right text-muted text-xs">₹{m.high} <span className="opacity-50">/</span> ₹{m.low}</td>
                    <td className={`py-2 text-right font-semibold ${m.return_pct >= 0 ? 'text-gain' : 'text-loss'}`}>
                      {m.return_pct >= 0 ? '+' : ''}{m.return_pct}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-surface border border-border rounded-xl p-5 space-y-3">
            <p className="label">AI MOVEMENT SUMMARY</p>
            <div className="text-text/90 text-sm leading-relaxed whitespace-pre-line font-normal">{narrative_summary}</div>
            {observations && observations.length > 0 && (
              <div className="pt-3 border-t border-border/40 space-y-2">
                <p className="text-[10px] font-bold text-gold tracking-wider uppercase">Key Observations</p>
                <ul className="list-disc list-inside space-y-1.5 text-xs text-text/80 leading-relaxed pl-1">
                  {observations.map((obs, index) => (
                    <li key={index} className="marker:text-gold">{obs}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div className="bg-surface border border-border rounded-xl p-5 space-y-4">
            <p className="label">CORPORATE ACTIONS IN {selectedYear}</p>
            <div className="space-y-3">
              <div>
                <p className="text-[10px] font-bold text-muted tracking-wider uppercase mb-2">Dividends</p>
                {corporate_actions.dividends.length > 0 ? (
                  <div className="space-y-2">
                    {corporate_actions.dividends.map((div, i) => (
                      <div key={i} className="flex justify-between items-center bg-canvas/30 border border-border/40 px-3 py-2 rounded-lg text-xs">
                        <span className="text-text font-medium">{div.description}</span>
                        <span className="text-muted font-data">{div.date}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-muted text-xs italic">No dividends announced in {selectedYear}.</p>
                )}
              </div>
              <div className="pt-2">
                <p className="text-[10px] font-bold text-muted tracking-wider uppercase mb-2">Splits & Bonuses</p>
                {corporate_actions.splits_and_bonuses.length > 0 ? (
                  <div className="space-y-2">
                    {corporate_actions.splits_and_bonuses.map((split, i) => (
                      <div key={i} className="flex justify-between items-center bg-canvas/30 border border-border/40 px-3 py-2 rounded-lg text-xs">
                        <span className="text-text font-medium">{split.description}</span>
                        <span className="text-muted font-data">{split.date}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-muted text-xs italic">No splits or bonus issues in {selectedYear}.</p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
