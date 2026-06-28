import { useState, useCallback } from 'react';
import * as XLSX from 'xlsx';

interface ParsedSheet {
  headers: string[];
  rows: Record<string, unknown>[];
  clientName: string;
  clientCode: string;
}

const REQUIRED_COLUMNS = [
  'ScripName',
  'NetQty',
  'BuyValue',
  'SellValue',
];

const OPTIONAL_COLUMNS = [
  'Brokerage',
  'STT',
];

const SYNONYMS: Record<string, string[]> = {
  ScripName: ['scripname', 'scrip name', 'stockname', 'stock name', 'company', 'company name', 'stock', 'name', 'symbol', 'ticker', 'instrument', 'scripcode', 'scrip code', 'code', 'isin'],
  NetQty: ['netqty', 'net qty', 'quantity', 'qty', 'shares', 'vol', 'volume', 'no of shares', 'no. of shares', 'units', 'buyqty', 'buy qty', 'sellqty', 'sell qty'],
  BuyValue: ['buyvalue', 'buy value', 'buyprice', 'buy price', 'purchase price', 'rate', 'price', 'value', 'amount'],
  SellValue: ['sellvalue', 'sell value', 'sellprice', 'sell price', 'sale price', 'rate', 'price', 'value', 'amount'],
  Brokerage: ['brokerage', 'broker', 'commission'],
  STT: ['stt', 'securities transaction tax', 'tax'],
};

// Fuzzy match columns (case-insensitive, partial match on synonyms)
function findColumn(headers: string[], target: string): string | null {
  const targetLower = target.toLowerCase();
  const synonyms = SYNONYMS[target] || [targetLower];
  
  // First pass: try exact match on standard synonyms
  for (const h of headers) {
    const hLower = h.toLowerCase().trim().replace(/[\s_]/g, ' ');
    for (const syn of synonyms) {
      const synClean = syn.toLowerCase().trim().replace(/[\s_]/g, ' ');
      if (hLower === synClean) {
        return h;
      }
    }
  }
  
  // Second pass: try partial match
  for (const h of headers) {
    const hLower = h.toLowerCase().trim().replace(/[\s_]/g, '');
    for (const syn of synonyms) {
      const synClean = syn.toLowerCase().trim().replace(/[\s_]/g, '');
      if (hLower.includes(synClean) || synClean.includes(hLower)) {
        return h;
      }
    }
  }
  return null;
}

export function useSheetParser() {
  const [parsed, setParsed] = useState<ParsedSheet | null>(null);
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [columnStatus, setColumnStatus] = useState<Record<string, { found: boolean; mappedTo: string | null }>>({});

  const parseFile = useCallback((file: File) => {
    setParsing(true);
    setError(null);

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = new Uint8Array(e.target?.result as ArrayBuffer);
        const workbook = XLSX.read(data, { type: 'array' });
        const sheetName = workbook.SheetNames[0];
        const sheet = workbook.Sheets[sheetName];
        const jsonData = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet, { defval: '' });

        if (jsonData.length === 0) {
          setError('The Excel sheet appears to be empty.');
          setParsing(false);
          return;
        }

        const headers = Object.keys(jsonData[0]);

        // Extract client info from first row
        let clientName = '';
        let clientCode = '';
        for (const h of headers) {
          const hLower = h.toLowerCase();
          if (hLower.includes('client name') || hLower.includes('clientname')) {
            clientName = String(jsonData[0][h] || '');
          }
          if (hLower.includes('client code') || hLower.includes('clientcode')) {
            clientCode = String(jsonData[0][h] || '');
          }
        }

        // Validate columns
        const status: Record<string, { found: boolean; mappedTo: string | null }> = {};
        for (const req of [...REQUIRED_COLUMNS, ...OPTIONAL_COLUMNS]) {
          const match = findColumn(headers, req);
          status[req] = { found: !!match, mappedTo: match };
        }
        setColumnStatus(status);

        setParsed({
          headers,
          rows: jsonData,
          clientName,
          clientCode,
        });
      } catch {
        setError('Failed to parse the Excel file. Please check the format.');
      } finally {
        setParsing(false);
      }
    };

    reader.onerror = () => {
      setError('Failed to read the file.');
      setParsing(false);
    };

    reader.readAsArrayBuffer(file);
  }, []);

  const updateMapping = useCallback((stdCol: string, header: string | null) => {
    setColumnStatus((prevStatus) => ({
      ...prevStatus,
      [stdCol]: { found: !!header, mappedTo: header }
    }));
  }, []);

  const allColumnsValid = REQUIRED_COLUMNS.every(
    (col) => columnStatus[col]?.found
  );

  return {
    parsed,
    parsing,
    error,
    parseFile,
    columnStatus,
    allColumnsValid,
    requiredColumns: REQUIRED_COLUMNS,
    optionalColumns: OPTIONAL_COLUMNS,
    updateMapping,
  };
}
