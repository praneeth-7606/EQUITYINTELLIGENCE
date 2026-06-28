import { useCallback, useRef, useState } from 'react';

import { useSheetParser } from '../../hooks/useSheetParser';
import { useAppStore } from '../../store/appStore';
import ColumnValidator from './ColumnValidator';

type UploadResult = {
  fileName: string;
  status: 'success' | 'failed';
  summary: string;
  sessionId?: string;
};

function maskStatementLabel(label?: string | null) {
  const text = (label || '').trim();
  if (!text) return 'Protected statement';
  const extIndex = text.lastIndexOf('.');
  const ext = extIndex >= 0 ? text.slice(extIndex).toLowerCase() : '';
  return `Protected statement${ext}`;
}

export default function SheetDropZone() {
  const {
    parseFile,
    parsed,
    parsing,
    error,
    columnStatus,
    allColumnsValid,
    requiredColumns,
    optionalColumns,
    updateMapping,
  } = useSheetParser();
  const { setFile, setRawData, setActiveSessionId } = useAppStore();
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadResults, setUploadResults] = useState<UploadResult[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const prepareFiles = useCallback((files: File[]) => {
    const validFiles = files.filter((file) => file.name.endsWith('.xlsx') || file.name.endsWith('.xls'));
    if (validFiles.length === 0) {
      setUploadError('Only .xlsx and .xls files are supported.');
      return;
    }

    setUploadError(validFiles.length !== files.length ? 'Some files were skipped because only Excel files are supported.' : null);
    setSelectedFiles(validFiles);
    setUploadResults([]);
    parseFile(validFiles[0]);
  }, [parseFile]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    prepareFiles(Array.from(e.dataTransfer.files));
  }, [prepareFiles]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      prepareFiles(files);
    }
  }, [prepareFiles]);

  const buildMappingPlan = useCallback(() => {
    if (!parsed) {
      return null;
    }

    return {
      layout_type: parsed.headers.includes('Buy date') && parsed.headers.includes('Sell date') ? 'matched_row' : 'standard_row',
      mappings: {
        symbol: columnStatus.ScripName?.mappedTo || null,
        quantity: columnStatus.NetQty?.mappedTo || null,
        buy_value: columnStatus.BuyValue?.mappedTo || null,
        sell_value: columnStatus.SellValue?.mappedTo || null,
        brokerage: columnStatus.Brokerage?.mappedTo || null,
        stt: columnStatus.STT?.mappedTo || null,
      },
    };
  }, [parsed, columnStatus]);

  const handleUpload = useCallback(async () => {
    if (!parsed || selectedFiles.length === 0) return;

    setUploading(true);
    setUploadError(null);
    setUploadResults([]);

    const token = localStorage.getItem('access_token');
    const headers: Record<string, string> = {};
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    const mappingPlan = buildMappingPlan();
    const results: UploadResult[] = [];
    let activeSessionChosen = false;

    try {
      for (let index = 0; index < selectedFiles.length; index += 1) {
        const file = selectedFiles[index];
        const formData = new FormData();
        formData.append('file', file);
        if (mappingPlan && index === 0) {
          formData.append('mapping_plan', JSON.stringify(mappingPlan));
        }

        const res = await fetch('/api/v1/upload', {
          method: 'POST',
          headers,
          body: formData,
        });
        const data = await res.json();

        if (data.success) {
          results.push({
            fileName: file.name,
            status: 'success',
            summary: data.summary || 'Upload completed.',
            sessionId: data.structured_data?.session_id,
          });

          if (!activeSessionChosen && data.structured_data?.session_id) {
            setFile(file, {
              clientName: maskStatementLabel(file.name),
              clientCode: 'masked',
              columns: parsed.headers,
              rowCount: parsed.rows.length,
              symbols: data.structured_data?.unique_symbols || [],
              startDate: data.structured_data?.start_date || '',
              endDate: data.structured_data?.end_date || '',
            });
            setRawData(parsed.rows);
            setActiveSessionId(data.structured_data.session_id);
            activeSessionChosen = true;
          }
        } else {
          results.push({
            fileName: file.name,
            status: 'failed',
            summary: data.summary || 'Upload failed.',
          });
        }
      }

      setUploadResults(results);

      const successCount = results.filter((item) => item.status === 'success').length;
      if (successCount === 0) {
        setUploadError('None of the selected sheets could be uploaded.');
      } else if (successCount < results.length) {
        setUploadError(`${successCount} of ${results.length} sheets uploaded successfully. Check the per-file results below.`);
      }
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Network error during upload.');
    } finally {
      setUploading(false);
    }
  }, [parsed, selectedFiles, buildMappingPlan, setFile, setRawData, setActiveSessionId]);

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="grid gap-8 xl:grid-cols-[1.06fr_0.94fr]">
        <section className="space-y-7">
          <div className="space-y-5">
            <div className="inline-flex items-center gap-3 rounded-full border border-[#d4a84c]/18 bg-[#d4a84c]/10 px-4 py-2 text-[11px] uppercase tracking-[0.24em] text-[#f2d18a]">
              <span className="h-2 w-2 rounded-full bg-[#d4a84c]" />
              Premium Statement Intake
            </div>
            <div className="space-y-4">
              <h1 className="font-display text-5xl leading-[0.95] text-[#f6f1e8] sm:text-6xl">
                Upload once. Analyze deeply. Track every stock decision.
              </h1>
              <p className="max-w-2xl text-base leading-7 text-[#d0c3ab]">
                Bring in one or many brokerage exports, validate the layout once, and turn every uploaded statement into its own reusable intelligence session for portfolio, dividend, P&amp;L, and stock-analysis workflows.
              </p>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            {[
              ['Statement intelligence', 'Normalize noisy broker formats into a clean portfolio schema your agents can trust.'],
              ['Multi-sheet support', 'Upload more than one statement at a time and create a separate reusable session for each sheet.'],
              ['Observable backend', 'Every upload, route decision, tool call, token count, latency, and result is traceable.'],
            ].map(([title, body]) => (
              <div key={title} className="rounded-[24px] border border-[#d4a84c]/10 bg-[linear-gradient(180deg,_rgba(255,255,255,0.04),_rgba(255,255,255,0.02))] p-5 shadow-[0_0_30px_rgba(181,140,63,0.04)] backdrop-blur">
                <p className="text-sm font-semibold text-[#f6f1e8]">{title}</p>
                <p className="mt-2 text-xs leading-5 text-[#b8ab94]">{body}</p>
              </div>
            ))}
          </div>

          {!parsed && (
            <div className="rounded-[30px] border border-[#d4a84c]/10 bg-[linear-gradient(180deg,_rgba(255,255,255,0.03),_rgba(255,255,255,0.01))] p-6 backdrop-blur-xl">
              <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[#a49a89]">Best For</p>
              <p className="mt-3 text-sm leading-6 text-[#d7cec0]">
                Zerodha, Angel One, Motilal, HDFC Securities, and other Excel exports that contain stock name, quantity, buy or sell values, brokerage, and STT-like fields.
              </p>
              <button
                onClick={() => {
                  setFile(new File([], 'empty.xlsx'), {
                    clientName: 'Guest Client',
                    clientCode: 'Direct stock mode',
                    columns: [],
                    rowCount: 0,
                    symbols: [],
                    startDate: '',
                    endDate: '',
                  });
                }}
                className="mt-5 rounded-full border border-[#d4a84c]/25 bg-[#d4a84c]/10 px-4 py-2 text-sm font-semibold text-[#f2d18a]"
              >
                Skip upload and analyze single stocks
              </button>
            </div>
          )}
        </section>

        <section className="rounded-[32px] border border-[#d4a84c]/10 bg-[radial-gradient(circle_at_top,_rgba(212,168,76,0.08),_transparent_25%),linear-gradient(180deg,_rgba(12,18,29,0.94),_rgba(7,11,19,0.96))] p-7 shadow-2xl shadow-black/40 backdrop-blur-2xl">
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => fileInputRef.current?.click()}
            className={`cursor-pointer rounded-[28px] border-2 border-dashed p-10 text-center transition ${
              isDragging
                ? 'border-[#d4a84c] bg-[#d4a84c]/10'
                : 'border-[#dbc9a2]/60 bg-[#07111b] hover:border-[#d4a84c]/60 hover:bg-white/[0.03]'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls"
              multiple
              onChange={handleInputChange}
              className="hidden"
              aria-label="Upload Excel files"
            />

            {parsing ? (
              <div className="space-y-4">
                <div className="mx-auto h-10 w-10 animate-spin rounded-full border-2 border-[#d4a84c] border-t-transparent" />
                <p className="text-sm text-[#d8cbb0]">Reading the first selected sheet and validating its structure...</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="mx-auto flex h-18 w-18 items-center justify-center rounded-3xl bg-gradient-to-br from-[#d4a84c]/18 to-[#0f766e]/20 px-6 py-5 text-2xl font-bold text-[#f7e2a5]">
                  XL
                </div>
                <div>
                  <p className="text-lg font-semibold text-[#f6f1e8]">
                    {isDragging ? 'Release to import the statements' : 'Drop one or more brokerage sheets here'}
                  </p>
                  <p className="mt-2 text-sm text-[#a49a89]">Or click to browse for `.xlsx` or `.xls` files</p>
                </div>
              </div>
            )}
          </div>

          {(error || uploadError) && (
            <div className="mt-5 rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
              {error || uploadError}
            </div>
          )}

          {parsed ? (
            <div className="mt-6 space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[#a49a89]">Validation</p>
                  <p className="mt-2 text-sm text-[#f6f1e8]">
                    {allColumnsValid ? 'The preview sheet is valid. Each uploaded file will become its own statement session.' : 'Map the missing columns to continue.'}
                  </p>
                </div>
                <div className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-[#d7cec0]">
                  {parsed.rows.length} rows | {parsed.headers.length} columns | {selectedFiles.length} file{selectedFiles.length === 1 ? '' : 's'}
                </div>
              </div>

              <ColumnValidator
                requiredColumns={requiredColumns}
                optionalColumns={optionalColumns}
                columnStatus={columnStatus}
                allHeaders={parsed.headers}
                onMapColumn={updateMapping}
              />

              {selectedFiles.length > 0 && (
                <div className="rounded-2xl border border-[#d4a84c]/10 bg-[#08111a] p-4">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[#a49a89]">Selected statement queue</p>
                  <div className="mt-3 grid gap-2">
                    {selectedFiles.slice(0, 6).map((file, index) => (
                      <div key={`${file.name}-${index}`} className="flex items-center justify-between rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2 text-sm text-[#e1d8ca]">
                        <span className="truncate">{maskStatementLabel(file.name)}</span>
                        
                        <span className="ml-3 text-xs text-[#b8ab94]">{index === 0 ? 'Preview source' : 'Queued'}</span>
                      </div>
                    ))}
                    {selectedFiles.length > 6 && (
                      <p className="text-xs text-[#a49a89]">+ {selectedFiles.length - 6} more files queued for upload</p>
                    )}
                  </div>
                </div>
              )}

              <button
                onClick={handleUpload}
                disabled={!allColumnsValid || uploading}
                className={`flex w-full items-center justify-center rounded-2xl px-4 py-3.5 text-sm font-semibold tracking-wide transition ${
                  allColumnsValid && !uploading
                    ? 'bg-gradient-to-r from-[#d4a84c] via-[#c88e32] to-[#0f766e] text-[#081018] shadow-lg shadow-[#d4a84c]/15 hover:brightness-105'
                    : 'cursor-not-allowed bg-[#1a2635] text-[#6f8392]'
                }`}
              >
                {uploading ? (
                  <span className="flex items-center gap-2">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-[#081018] border-t-transparent" />
                    Uploading {selectedFiles.length} sheet{selectedFiles.length === 1 ? '' : 's'} and preparing statement sessions...
                  </span>
                ) : (
                  `Upload ${selectedFiles.length || 1} sheet${selectedFiles.length === 1 ? '' : 's'}`
                )}
              </button>

              {uploadResults.length > 0 && (
                <div className="rounded-2xl border border-[#d4a84c]/10 bg-[#08111a] p-4">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[#a49a89]">Upload results</p>
                  <div className="mt-3 grid gap-2">
                    {uploadResults.map((result) => (
                      <div
                        key={`${result.fileName}-${result.status}`}
                        className={`rounded-xl border px-3 py-3 text-sm ${
                          result.status === 'success'
                            ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-200'
                            : 'border-rose-500/20 bg-rose-500/10 text-rose-200'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="font-semibold">{maskStatementLabel(result.fileName)}</span>
                          
                          <span className="text-xs uppercase tracking-[0.18em]">{result.status}</span>
                        </div>
                        <p className="mt-2 text-xs leading-5 opacity-90">{result.summary}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              {[
                'Each uploaded sheet becomes its own reusable statement session.',
                'The backend records upload steps, agent routing, token use, latency, and final output.',
              ].map((item) => (
                <div key={item} className="rounded-2xl border border-[#d4a84c]/10 bg-[#08111a] px-4 py-4 text-sm leading-6 text-[#d7cec0]">
                  {item}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
