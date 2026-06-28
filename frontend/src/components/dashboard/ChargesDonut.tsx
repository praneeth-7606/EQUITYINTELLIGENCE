import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { useAppStore } from '../../store/appStore';
import { formatInr } from '../../lib/formatInr';

const COLORS = ['#D4A017', '#E84848', '#1BCA8A', '#8899BB', '#E8C547', '#162A52'];

export default function ChargesDonut() {
  const { tables } = useAppStore();

  const data = tables.charges.map((row, i) => ({
    name: String(row['charge_type'] || row['type'] || `Charge ${i + 1}`),
    value: Math.abs(Number(row['amount'] || 0)),
  })).filter((d) => d.value > 0);

  const total = data.reduce((sum, d) => sum + d.value, 0);

  if (data.length === 0) {
    return (
      <div className="bg-surface border border-border rounded-xl p-8 flex items-center justify-center h-[300px]">
        <p className="text-muted text-sm">No charges data available yet.</p>
      </div>
    );
  }

  return (
    <div className="bg-surface border border-border rounded-xl p-4">
      <p className="label mb-4">CHARGES BREAKDOWN</p>
      <div className="relative">
        <ResponsiveContainer width="100%" height={280}>
          <PieChart>
            <Pie
              data={data}
              innerRadius={70}
              outerRadius={100}
              paddingAngle={3}
              dataKey="value"
              stroke="none"
            >
              {data.map((_entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                background: '#0F2040',
                border: '1px solid #1B3A6B',
                borderRadius: '8px',
                fontSize: '12px',
                fontFamily: 'JetBrains Mono',
                color: '#E8EDF5',
              }}
              formatter={(value: any) => formatInr(Number(value || 0))}
            />
          </PieChart>
        </ResponsiveContainer>
        {/* Center label */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-center">
            <p className="label text-[8px]">TOTAL</p>
            <p className="font-display text-lg text-text">{formatInr(total)}</p>
          </div>
        </div>
      </div>
      {/* Legend */}
      <div className="flex flex-wrap gap-3 mt-2 justify-center">
        {data.map((d, i) => (
          <div key={d.name} className="flex items-center gap-1.5">
            <span
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: COLORS[i % COLORS.length] }}
            />
            <span className="text-muted text-[10px]">{d.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
