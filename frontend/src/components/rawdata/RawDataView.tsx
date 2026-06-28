import { useState, useMemo } from 'react';
import { useAppStore } from '../../store/appStore';

export default function RawDataView() {
  const { rawData, columns } = useAppStore();
  const [searchTerm, setSearchTerm] = useState('');
  const [typeFilter, setTypeFilter] = useState<'all' | 'buy' | 'sell'>('all');

  const filteredData = useMemo(() => {
    return rawData.filter((row) => {
      // Search filter
      const scripName = String(row['ScripName'] || row['Scrip Name'] || row['scrip_name'] || '').toLowerCase();
      if (searchTerm && !scripName.includes(searchTerm.toLowerCase())) return false;

      // Type filter
      const netQty = Number(row['NetQty'] || row['Net Qty'] || row['net_qty'] || 0);
      if (typeFilter === 'buy' && netQty <= 0) return false;
      if (typeFilter === 'sell' && netQty >= 0) return false;

      return true;
    });
  }, [rawData, searchTerm, typeFilter]);

  const displayColumns = columns.length > 0
    ? columns.slice(0, 12)  // Limit visible columns
    : ['Date', 'ScripName', 'Exchange', 'NetQty', 'BuyValue', 'SellValue', 'Brokerage', 'STT'];

  if (rawData.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-center space-y-3 max-w-sm">
          <div className="text-4xl">📋</div>
          <h2 className="text-text text-lg font-semibold">Raw Data</h2>
          <p className="text-muted text-sm leading-relaxed">
            Upload an Excel sheet to view parsed transaction data.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden p-5">
      {/* Controls */}
      <div className="flex items-center gap-3 mb-4 shrink-0 flex-wrap">
        <input
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Search by scrip name…"
          className="bg-canvas border border-border rounded-lg px-3 py-2 text-sm text-text
                     placeholder-muted/60 focus:border-gold focus:outline-none w-64"
        />
        <div className="flex gap-1">
          {(['all', 'buy', 'sell'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTypeFilter(t)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all uppercase tracking-wider
                ${typeFilter === t
                  ? 'bg-raised text-gold border border-gold/30'
                  : 'text-muted hover:text-text border border-transparent'
                }`}
            >
              {t}
            </button>
          ))}
        </div>
        <span className="text-muted text-xs ml-auto font-data">
          {filteredData.length} / {rawData.length} rows
        </span>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto bg-surface border border-border rounded-xl">
        <table className="w-full text-xs min-w-[800px]">
          <thead className="sticky top-0 bg-surface z-10">
            <tr className="border-b border-border">
              {displayColumns.map((col) => (
                <th key={col} scope="col" className="label px-3 py-2.5 text-left whitespace-nowrap">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredData.map((row, rowIdx) => {
              const netQty = Number(row['NetQty'] || row['Net Qty'] || row['net_qty'] || 0);
              const isBuy = netQty > 0;
              const isSell = netQty < 0;

              return (
                <tr
                  key={rowIdx}
                  className={`border-b border-border/20 hover:bg-raised/30 transition-colors
                    ${isBuy ? 'border-l-2 border-l-gain' : ''}
                    ${isSell ? 'border-l-2 border-l-loss' : ''}
                  `}
                >
                  {displayColumns.map((col) => {
                    const cellValue = row[col];

                    // Special rendering for trade type
                    if ((col === 'NetQty' || col === 'Net Qty') && typeof cellValue === 'number') {
                      return (
                        <td key={col} className="px-3 py-2">
                          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-medium
                            ${cellValue > 0
                              ? 'bg-gainbg text-gain'
                              : 'bg-lossbg text-loss'
                            }`}
                          >
                            {cellValue > 0 ? 'BUY' : 'SELL'} {Math.abs(cellValue)}
                          </span>
                        </td>
                      );
                    }

                    return (
                      <td key={col} className="px-3 py-2 text-text font-data whitespace-nowrap">
                        {cellValue != null ? String(cellValue) : '—'}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
