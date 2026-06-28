import { create } from 'zustand';

export interface KPI {
  label: string;
  value: string;
  type: 'gain' | 'loss' | 'neutral';
}

export interface Step {
  step_num: number;
  thought?: string;
  action?: string;
  tool_input?: string;
  observation?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'agent';
  content: string;
  agentUsed?: string;
  confidence?: string;
  routed?: boolean;
  kpis?: KPI[];
  steps?: Step[];
  structuredData?: Record<string, unknown>;
  insights?: string[];
  executionTime?: number;
  timestamp: number;
}

export type TableId = 'open' | 'realised' | 'charges' | 'trades';
export type Row = Record<string, unknown>;

export type Tab = 'chat' | 'dashboard' | 'raw';
export type AgentSelection = 'auto' | 'portfolio' | 'pnl' | 'dividend' | 'stock_analysis';

interface UploadMeta {
  clientName: string;
  clientCode: string;
  columns: string[];
  rowCount: number;
  symbols: string[];
  startDate: string;
  endDate: string;
}

interface AppState {
  // File
  file: File | null;
  uploaded: boolean;
  clientName: string;
  clientCode: string;
  columns: string[];
  rowCount: number;
  symbols: string[];
  startDate: string;
  endDate: string;
  rawData: Record<string, unknown>[];

  // Agent
  selectedAgent: AgentSelection;
  lastRoute: { agent: string; confidence: string } | null;

  // Chat
  messages: Message[];
  isStreaming: boolean;
  activeSessionId: string | null;
  userSessions: any[];

  // Live data
  kpis: KPI[];
  tables: Record<TableId, Row[]>;
  reactSteps: Step[];

  // Tab
  activeTab: Tab;

  // Actions
  setFile: (f: File, meta: UploadMeta) => void;
  setRawData: (data: Record<string, unknown>[]) => void;
  setSelectedAgent: (agent: AgentSelection) => void;
  setActiveTab: (tab: Tab) => void;
  addMessage: (msg: Message) => void;
  updateLastMessage: (content: string) => void;
  setStreaming: (v: boolean) => void;
  pushKPI: (kpi: KPI) => void;
  setKPIs: (kpis: KPI[]) => void;
  pushTableRow: (tableId: TableId, row: Row) => void;
  setTableRows: (tableId: TableId, rows: Row[]) => void;
  pushStep: (step: Step) => void;
  setSteps: (steps: Step[]) => void;
  clearRun: () => void;
  reset: () => void;
  setSessions: (sessions: any[]) => void;
  setActiveSessionId: (sessionId: string | null) => void;
  loadSessionHistory: (sessionId: string) => Promise<void>;

  // Cancel/Abort
  abort: (() => void) | null;
  setAbort: (fn: (() => void) | null) => void;
}

const initialTables: Record<TableId, Row[]> = {
  open: [],
  realised: [],
  charges: [],
  trades: [],
};

export const useAppStore = create<AppState>((set) => ({
  // File
  file: null,
  uploaded: false,
  clientName: '',
  clientCode: '',
  columns: [],
  rowCount: 0,
  symbols: [],
  startDate: '',
  endDate: '',
  rawData: [],

  // Agent
  selectedAgent: 'auto',
  lastRoute: null,

  // Chat
  messages: [],
  isStreaming: false,
  activeSessionId: null,
  userSessions: [],

  // Live data
  kpis: [],
  tables: { ...initialTables },
  reactSteps: [],

  // Tab
  activeTab: 'chat',

  // Actions
  setFile: (f, meta) =>
    set({
      file: f,
      uploaded: true,
      clientName: meta.clientName,
      clientCode: meta.clientCode,
      columns: meta.columns,
      rowCount: meta.rowCount,
      symbols: meta.symbols,
      startDate: meta.startDate,
      endDate: meta.endDate,
      activeTab: 'chat',
    }),

  setRawData: (data) => set({ rawData: data }),

  setSelectedAgent: (agent) => set({ selectedAgent: agent }),

  setActiveTab: (tab) => set({ activeTab: tab }),

  addMessage: (msg) =>
    set((state) => ({ messages: [...state.messages, msg] })),

  updateLastMessage: (content) =>
    set((state) => {
      const msgs = [...state.messages];
      if (msgs.length > 0) {
        msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content };
      }
      return { messages: msgs };
    }),

  setStreaming: (v) => set({ isStreaming: v }),

  pushKPI: (kpi) =>
    set((state) => ({ kpis: [...state.kpis, kpi] })),

  setKPIs: (kpis) => set({ kpis }),

  pushTableRow: (tableId, row) =>
    set((state) => ({
      tables: {
        ...state.tables,
        [tableId]: [...state.tables[tableId], row],
      },
    })),

  setTableRows: (tableId, rows) =>
    set((state) => ({
      tables: { ...state.tables, [tableId]: rows },
    })),

  pushStep: (step) =>
    set((state) => ({ reactSteps: [...state.reactSteps, step] })),

  setSteps: (steps) => set({ reactSteps: steps }),

  clearRun: () =>
    set({
      kpis: [],
      tables: { ...initialTables },
      reactSteps: [],
    }),

  setSessions: (sessions) => set({ userSessions: sessions }),
  setActiveSessionId: (sessionId) => set({ activeSessionId: sessionId }),
  loadSessionHistory: async (sessionId) => {
    try {
      const token = localStorage.getItem('access_token');
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      const [historyRes, sessionsRes] = await Promise.all([
        fetch(`/api/v1/chat/history/${sessionId}`, { headers }),
        fetch('/api/v1/user/sessions', { headers }),
      ]);
      const data = await historyRes.json();
      const sessionsData = await sessionsRes.json();
      const matchingSession = sessionsData?.success && Array.isArray(sessionsData.sessions)
        ? sessionsData.sessions.find((session: any) => session._id === sessionId)
        : null;

      if (data.success && Array.isArray(data.messages)) {
        set({ 
          messages: data.messages, 
          activeSessionId: sessionId,
          uploaded: true,
          clientName: matchingSession?.original_filename || 'Statement session',
          clientCode: matchingSession?.conversation_name || '',
          activeTab: 'chat',
        });
      }
    } catch (err) {
      console.error('Failed to load session history:', err);
    }
  },

  // Cancel/Abort
  abort: null,
  setAbort: (fn) => set({ abort: fn }),

  reset: () =>
    set({
      file: null,
      uploaded: false,
      clientName: '',
      clientCode: '',
      columns: [],
      rowCount: 0,
      symbols: [],
      startDate: '',
      endDate: '',
      rawData: [],
      selectedAgent: 'auto',
      lastRoute: null,
      messages: [],
      isStreaming: false,
      kpis: [],
      tables: { ...initialTables },
      reactSteps: [],
      activeTab: 'chat',
      abort: null,
      activeSessionId: null,
    }),
}));
