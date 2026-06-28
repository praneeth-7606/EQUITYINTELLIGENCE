import type { Row } from '../../store/appStore';

interface Column {
  key: string;
  label: string;
  align: 'left' | 'right';
}

interface RowStreamTableProps {
  columns: Column[];
  rows: Row[];
  tableId: string;
  caption?: string;
}

export default function RowStreamTable({ columns, rows, tableId, caption }: RowStreamTableProps) {
  if (rows.length === 0) {
    return (
      <div className="bg-surface border border-border rounded-xl p-6 text-center">
        <p className="text-muted text-sm">No data available for {caption || tableId}.</p>
      </div>
    );
  }

  return (
    <div className="bg-surface border border-border rounded-xl overflow-hidden">
      <table className="w-full text-sm" aria-label={caption || tableId}>
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="border-b border-border">
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                className={`label px-4 py-2.5 ${col.align === 'right' ? 'text-right' : 'text-left'}`}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIdx) => {
            // Determine if this is a gain or loss row
            const pnlValue = row['pnl'] ?? row['net_pnl'] ?? row['unrealised_pnl'] ?? row['gross_pnl'];
            const isGain = typeof pnlValue === 'number' ? pnlValue > 0 : false;
            const isLoss = typeof pnlValue === 'number' ? pnlValue < 0 : false;

            return (
              <tr
                key={rowIdx}
                className={`border-b border-border/30 last:border-0 row-enter
                  ${isGain ? 'border-l-2 border-l-gain' : ''}
                  ${isLoss ? 'border-l-2 border-l-loss' : ''}
                `}
                style={{ animationDelay: `${rowIdx * 50}ms` }}
              >
                {columns.map((col) => {
                  const cellValue = row[col.key];
                  const isNumber = typeof cellValue === 'number';
                  const isPositive = isNumber && cellValue > 0;
                  const isNegative = isNumber && cellValue < 0;
                  const isPnlCol = col.key.toLowerCase().includes('pnl') || col.key.toLowerCase().includes('return');

                  let cellClass = 'px-4 py-2.5 ';
                  cellClass += col.align === 'right' ? 'text-right ' : 'text-left ';
                  cellClass += isNumber ? 'data-num text-xs ' : 'text-xs text-text ';

                  if (isPnlCol && isPositive) {
                    cellClass += 'text-gain bg-gainbg/30 ';
                  } else if (isPnlCol && isNegative) {
                    cellClass += 'text-loss bg-lossbg/30 ';
                  }

                  const display = isNumber
                    ? cellValue.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                    : String(cellValue ?? '—');

                  return (
                    <td key={col.key} className={cellClass}>
                      {isPnlCol && isPositive && '✓ '}
                      {isPnlCol && isNegative && '✗ '}
                      {display}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
