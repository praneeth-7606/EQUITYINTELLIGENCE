import { useMemo } from 'react';

interface MarkdownRendererProps {
  content: string;
}

function cleanMarkdown(content: string): string {
  return (content || '')
    .trim()
    .replace(/^```(?:markdown|md|text)?\s*/i, '')
    .replace(/\s*```$/i, '')
    .replace(/\{\{current_date\}\}/g, new Date().toISOString().slice(0, 10))
    .replace(/\{current_date\}/g, new Date().toISOString().slice(0, 10))
    .trim();
}

export default function MarkdownRenderer({ content }: MarkdownRendererProps) {
  const blocks = useMemo(() => {
    if (!content) return [];
    
    const lines = cleanMarkdown(content).split('\n');
    const resultBlocks: { type: string; content: string[] | string }[] = [];
    
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.trim();
      
      if (!trimmed) {
        i++;
        continue;
      }
      
      // Horizontal Rule
      if (trimmed === '---' || trimmed === '***') {
        resultBlocks.push({ type: 'hr', content: '' });
        i++;
        continue;
      }
      
      // Headings
      if (trimmed.startsWith('### ')) {
        resultBlocks.push({ type: 'h3', content: trimmed.slice(4) });
        i++;
        continue;
      }
      if (trimmed.startsWith('#### ')) {
        resultBlocks.push({ type: 'h4', content: trimmed.slice(5) });
        i++;
        continue;
      }
      if (trimmed.startsWith('# ') || trimmed.startsWith('## ')) {
        const title = trimmed.startsWith('# ') ? trimmed.slice(2) : trimmed.slice(3);
        resultBlocks.push({ type: 'h2', content: title });
        i++;
        continue;
      }
      
      // Lists
      if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
        const listItems: string[] = [];
        while (i < lines.length && (lines[i].trim().startsWith('- ') || lines[i].trim().startsWith('* '))) {
          listItems.push(lines[i].trim().slice(2));
          i++;
        }
        resultBlocks.push({ type: 'ul', content: listItems });
        continue;
      }
      
      // Tables
      if (trimmed.startsWith('|')) {
        const tableLines: string[] = [];
        while (i < lines.length && lines[i].trim().startsWith('|')) {
          tableLines.push(lines[i].trim());
          i++;
        }
        resultBlocks.push({ type: 'table', content: tableLines });
        continue;
      }
      
      // Default: Paragraph block (group consecutive normal lines)
      const paraLines: string[] = [];
      while (i < lines.length && 
             lines[i].trim() && 
             !lines[i].trim().startsWith('|') && 
             !lines[i].trim().startsWith('- ') && 
             !lines[i].trim().startsWith('* ') && 
             !lines[i].trim().startsWith('#') && 
             lines[i].trim() !== '---') {
        paraLines.push(lines[i]);
        i++;
      }
      resultBlocks.push({ type: 'p', content: paraLines.join('\n') });
    }
    
    return resultBlocks;
  }, [content]);

  // Helper to render inline markdown like bolding
  const renderInline = (text: string) => {
    if (!text) return '';
    // Replace **text** with <strong>text</strong>
    const parts = text.split('**');
    return parts.map((part, index) => {
      if (index % 2 === 1) {
        return <strong key={index} className="font-semibold text-text">{part}</strong>;
      }
      return part;
    });
  };

  return (
    <div className="space-y-3 font-sans text-sm text-text leading-relaxed">
      {blocks.map((block, idx) => {
        switch (block.type) {
          case 'hr':
            return <hr key={idx} className="border-border/50 my-4" />;
          case 'h2':
            return <h2 key={idx} className="text-lg font-bold text-text mt-4 mb-2 tracking-tight">{renderInline(block.content as string)}</h2>;
          case 'h3':
            return <h3 key={idx} className="text-base font-semibold text-text mt-4 mb-2">{renderInline(block.content as string)}</h3>;
          case 'h4':
            return <h4 key={idx} className="text-sm font-semibold text-text mt-3 mb-1.5">{renderInline(block.content as string)}</h4>;
          case 'ul':
            return (
              <ul key={idx} className="list-disc pl-5 space-y-1 my-2">
                {(block.content as string[]).map((item, itemIdx) => (
                  <li key={itemIdx} className="text-muted/90 text-sm leading-relaxed">
                    {renderInline(item)}
                  </li>
                ))}
              </ul>
            );
          case 'table': {
            const rows = block.content as string[];
            if (rows.length === 0) return null;
            
            // First row is header
            const parseRow = (rowStr: string) => {
              return rowStr
                .split('|')
                .slice(1, -1) // remove empty first and last elements
                .map((cell) => cell.trim());
            };
            
            const headers = parseRow(rows[0]);
            
            // Second row is separator e.g. |:---|:---|
            let dataRows = rows.slice(1);
            if (dataRows.length > 0 && dataRows[0].includes('---')) {
              dataRows = dataRows.slice(1); // skip separator row
            }
            
            return (
              <div key={idx} className="overflow-x-auto my-3 border border-border/50 rounded-xl bg-canvas/30">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-canvas border-b border-border/40">
                      {headers.map((h, hIdx) => (
                        <th key={hIdx} className="px-4 py-2.5 font-semibold text-muted tracking-wider uppercase text-[10px]">
                          {renderInline(h)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {dataRows.map((rowStr, rowIdx) => {
                      const cells = parseRow(rowStr);
                      return (
                        <tr key={rowIdx} className="border-b border-border/20 hover:bg-canvas/20 transition-colors">
                          {cells.map((cell, cellIdx) => (
                            <td key={cellIdx} className="px-4 py-2.5 text-text font-medium">
                              {renderInline(cell)}
                            </td>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            );
          }
          case 'p':
          default:
            return (
              <p key={idx} className="text-sm text-text whitespace-pre-wrap leading-relaxed">
                {renderInline(block.content as string)}
              </p>
            );
        }
      })}
    </div>
  );
}
