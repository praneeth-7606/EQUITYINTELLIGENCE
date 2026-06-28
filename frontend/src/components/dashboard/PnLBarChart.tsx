import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts';
import { useAppStore } from '../../store/appStore';

export default function PnLBarChart() {
  const { tables } = useAppStore();

  // Combine open and realised for P&L visualization
  const data = [
    ...tables.realised.map((row) => ({
      name: String(row['scrip'] || row['stock'] || row['scrip_name'] || 'Unknown'),
      gross_pnl: Number(row['gross_pnl'] || row['net_pnl'] || 0),
      net_pnl: Number(row['net_pnl'] || row['gross_pnl'] || 0),
    })),
    ...tables.open.map((row) => ({
      name: String(row['scrip'] || row['stock'] || row['scrip_name'] || 'Unknown'),
      gross_pnl: Number(row['unrealised_pnl'] || 0),
      net_pnl: Number(row['unrealised_pnl'] || 0),
    })),
  ];

  if (data.length === 0) {
    return (
      <div className="bg-surface border border-border rounded-xl p-8 flex items-center justify-center h-[300px]">
        <p className="text-muted text-sm">No P&L data available yet.</p>
      </div>
    );
  }

  return (
    <div className="bg-surface border border-border rounded-xl p-4">
      <p className="label mb-4">P&L BY STOCK</p>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1B3A6B" />
          <XAxis
            dataKey="name"
            tick={{ fill: '#8899BB', fontSize: 10, fontFamily: 'Inter' }}
            axisLine={{ stroke: '#1B3A6B' }}
            tickLine={false}
            interval={0}
            angle={-30}
            textAnchor="end"
            height={60}
          />
          <YAxis
            tick={{ fill: '#8899BB', fontSize: 10, fontFamily: 'JetBrains Mono' }}
            axisLine={{ stroke: '#1B3A6B' }}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: '#0F2040',
              border: '1px solid #1B3A6B',
              borderRadius: '8px',
              fontSize: '12px',
              fontFamily: 'JetBrains Mono',
              color: '#E8EDF5',
            }}
          />
          <ReferenceLine y={0} stroke="#1B3A6B" strokeWidth={2} />
          <Bar dataKey="gross_pnl" fill="#1B3A6B" radius={[4, 4, 0, 0]} name="Gross P&L" />
          <Bar dataKey="net_pnl" fill="#D4A017" radius={[4, 4, 0, 0]} name="Net P&L" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
