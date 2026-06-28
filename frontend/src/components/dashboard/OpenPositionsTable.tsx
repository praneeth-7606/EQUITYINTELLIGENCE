import { useAppStore } from '../../store/appStore';
import RowStreamTable from '../shared/RowStreamTable';

export default function OpenPositionsTable() {
  const { tables } = useAppStore();

  const columns = [
    { key: 'scrip_name', label: 'Stock', align: 'left' as const },
    { key: 'qty', label: 'Qty', align: 'right' as const },
    { key: 'avg_cost', label: 'Avg Cost', align: 'right' as const },
    { key: 'days_held', label: 'Days Held', align: 'right' as const },
    { key: 'total_invested', label: 'Total Invested', align: 'right' as const },
    { key: 'cmp', label: 'CMP', align: 'right' as const },
    { key: 'unrealised_pnl', label: 'Unrealised P&L', align: 'right' as const },
  ];

  return (
    <div>
      <p className="label mb-3">OPEN POSITIONS</p>
      <RowStreamTable
        columns={columns}
        rows={tables.open}
        tableId="open"
        caption="Open positions"
      />
    </div>
  );
}
