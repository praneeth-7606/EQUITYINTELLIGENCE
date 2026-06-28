import { useAppStore } from '../../store/appStore';
import RowStreamTable from '../shared/RowStreamTable';

export default function RealisedTradesTable() {
  const { tables } = useAppStore();

  const columns = [
    { key: 'scrip_name', label: 'Stock', align: 'left' as const },
    { key: 'buy_date', label: 'Buy Date', align: 'left' as const },
    { key: 'sell_date', label: 'Sell Date', align: 'left' as const },
    { key: 'qty', label: 'Qty', align: 'right' as const },
    { key: 'buy_value', label: 'Buy Value', align: 'right' as const },
    { key: 'sell_value', label: 'Sell Value', align: 'right' as const },
    { key: 'net_pnl', label: 'Net P&L', align: 'right' as const },
    { key: 'return_pct', label: 'Return %', align: 'right' as const },
  ];

  return (
    <div>
      <p className="label mb-3">REALISED TRADES</p>
      <RowStreamTable
        columns={columns}
        rows={tables.realised}
        tableId="realised"
        caption="Realised trades"
      />
    </div>
  );
}
