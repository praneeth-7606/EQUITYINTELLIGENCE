interface ColumnValidatorProps {
  requiredColumns: string[];
  optionalColumns: string[];
  columnStatus: Record<string, { found: boolean; mappedTo: string | null }>;
  allHeaders: string[];
  onMapColumn: (stdCol: string, header: string | null) => void;
}

export default function ColumnValidator({
  requiredColumns,
  optionalColumns,
  columnStatus,
  allHeaders,
  onMapColumn,
}: ColumnValidatorProps) {
  const allColumns = [
    ...requiredColumns.map((col) => ({ name: col, required: true })),
    ...optionalColumns.map((col) => ({ name: col, required: false })),
  ];

  return (
    <div className="bg-surface rounded-xl border border-border overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-canvas/35">
            <th className="label text-left px-4 py-2.5">Column Name</th>
            <th className="label text-left px-4 py-2.5">Requirement</th>
            <th className="label text-left px-4 py-2.5">Status</th>
            <th className="label text-left px-4 py-2.5">Mapped To Column</th>
          </tr>
        </thead>
        <tbody>
          {allColumns.map(({ name, required }) => {
            const status = columnStatus[name];
            return (
              <tr key={name} className="border-b border-border/50 last:border-0 hover:bg-canvas/10 transition-colors">
                <td className="px-4 py-2.5 text-text font-semibold text-xs">{name}</td>
                <td className="px-4 py-2.5">
                  {required ? (
                    <span className="text-muted text-[10px] uppercase font-bold tracking-wider">Required</span>
                  ) : (
                    <span className="text-muted/65 text-[10px] uppercase font-bold tracking-wider">Optional</span>
                  )}
                </td>
                <td className="px-4 py-2.5">
                  {status?.found ? (
                    <span className="text-gain text-xs font-semibold">✓ Found</span>
                  ) : required ? (
                    <span className="text-loss text-xs font-semibold">✗ Missing</span>
                  ) : (
                    <span className="text-muted/60 text-xs font-medium">— Empty</span>
                  )}
                </td>
                <td className="px-4 py-2.5">
                  <select
                    value={status?.mappedTo || ''}
                    onChange={(e) => onMapColumn(name, e.target.value || null)}
                    className="bg-raised text-text text-xs border border-border rounded-lg px-2.5 py-1.5
                               focus:border-gold focus:outline-none w-full max-w-[220px] transition-colors"
                  >
                    <option value="">Select column…</option>
                    {allHeaders.map((h) => (
                      <option key={h} value={h}>{h}</option>
                    ))}
                  </select>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
