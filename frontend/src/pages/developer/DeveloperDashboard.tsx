import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AccessTime,
  ArrowBack,
  AttachMoney,
  AutoAwesome,
  BarChart,
  Build,
  ChatBubbleOutlined,
  Description,
  History,
  Layers,
  PlayArrow,
  Psychology,
  ReportProblem,
  Search,
  SmartToy,
  Storage,
  Timeline as TimelineIcon,
} from '@mui/icons-material';
import { api } from '../../api/client';

type PanelKey =
  | 'live'
  | 'history'
  | 'trace'
  | 'tools'
  | 'llms'
  | 'agents'
  | 'errors'
  | 'cost'
  | 'perf'
  | 'replay';

type TraceSummary = {
  trace_id: string;
  timestamp: string;
  query: string;
  agent: string;
  status: string;
  latency_ms: number;
  total_tokens: number;
  cost_usd: number;
};

const iconStyle = { fontSize: 16 };

const panels: Array<{ key: PanelKey; label: string; icon: any }> = [
  { key: 'live', label: '01 Live', icon: <Layers style={iconStyle} /> },
  { key: 'history', label: '02 History', icon: <History style={iconStyle} /> },
  { key: 'trace', label: '03 Trace', icon: <TimelineIcon style={iconStyle} /> },
  { key: 'tools', label: '04 Tools', icon: <Build style={iconStyle} /> },
  { key: 'llms', label: '05 LLMs', icon: <Psychology style={iconStyle} /> },
  { key: 'agents', label: '06 Agents', icon: <SmartToy style={iconStyle} /> },
  { key: 'errors', label: '07 Errors', icon: <ReportProblem style={iconStyle} /> },
  { key: 'cost', label: '08 Cost', icon: <AttachMoney style={iconStyle} /> },
  { key: 'perf', label: '09 Perf', icon: <BarChart style={iconStyle} /> },
  { key: 'replay', label: '10 Replay', icon: <PlayArrow style={iconStyle} /> },
];

const agentNames: Record<string, string> = {
  excel_reader_tool: 'Excel Upload Pipeline',
  portfolio_agent: 'Portfolio Agent',
  pnl_agent: 'P&L Agent',
  dividend_agent: 'Dividend Agent',
  stock_analysis_agent: 'Stock Analysis Agent',
  supervisor: 'Supervisor',
  unknown: 'Unknown Agent',
};

const agentColors: Record<string, string> = {
  excel_reader_tool: '#38bdf8',
  portfolio_agent: '#22c55e',
  pnl_agent: '#f59e0b',
  dividend_agent: '#a78bfa',
  stock_analysis_agent: '#f472b6',
  unknown: '#94a3b8',
};

function fmtLatency(ms?: number) {
  const value = Number(ms || 0);
  return value < 1000 ? `${Math.round(value)}ms` : `${(value / 1000).toFixed(1)}s`;
}

function fmtCost(usd?: number) {
  const value = Number(usd || 0);
  return `$${value.toFixed(value < 0.01 ? 5 : 4)}`;
}

function fmtTokens(tokens?: number) {
  const value = Number(tokens || 0);
  return value >= 1000 ? `${(value / 1000).toFixed(1)}K` : `${value}`;
}

function cleanPreview(text?: string) {
  return (text || '')
    .trim()
    .replace(/^```(?:markdown|md|text)?\s*/i, '')
    .replace(/\s*```$/i, '')
    .replace(/\{\{current_date\}\}/g, new Date().toISOString().slice(0, 10))
    .replace(/\{current_date\}/g, new Date().toISOString().slice(0, 10))
    .replace(/#{1,6}\s*/g, '')
    .replace(/\*\*/g, '')
    .replace(/\*/g, '')
    .replace(/\|/g, ' ')
    .replace(/\b[A-Z]{5}\d{4}[A-Z]\b/gi, '<masked-pan>')
    .replace(/\b\d{8,}\b/g, '<masked-id>')
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, '<masked-email>')
    .replace(/(client\s*name\s*[:=-]\s*)([^\n,]+)/gi, '$1<masked-client>')
    .replace(/(client\s*code\s*[:=-]\s*)([^\n,]+)/gi, '$1<masked-code>')
    .replace(/(username\s*[:=-]\s*)([^\n,]+)/gi, '$1<masked-user>')
    .replace(/\s+/g, ' ')
    .trim();
}

function cleanAgent(agent?: string) {
  return agentNames[agent || 'unknown'] || agent || 'Unknown Agent';
}

function eventTime(value?: string) {
  if (!value) return '';
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function buildEvents(trace: any) {
  const events: any[] = [];

  events.push({
    kind: 'request',
    title: trace?.user_request?.selected_agent === 'excel_reader_tool' ? 'User uploaded an Excel sheet' : 'User sent a query',
    detail: cleanPreview(trace?.user_request?.original_prompt) || 'Request received by FastAPI',
    latency_ms: 0,
    status: trace?.status || 'running',
    icon: trace?.user_request?.selected_agent === 'excel_reader_tool' ? 'file' : 'message',
    time: trace?.created_at,
  });

  if (trace?.supervisor?.agent_selected) {
    events.push({
      kind: 'supervisor',
      title: `Supervisor selected ${cleanAgent(trace.supervisor.agent_selected)}`,
      detail: cleanPreview(trace.supervisor.reasoning) || 'The router inspected the query and selected the specialist agent.',
      latency_ms: 0,
      status: 'success',
      icon: 'bot',
      time: trace.supervisor.logged_at,
    });
  }

  (trace?.workflow_steps || []).forEach((step: any) => {
    events.push({
      kind: 'step',
      title: step.step_name,
      detail: explainStep(step),
      latency_ms: step.latency_ms,
      status: step.status,
      metadata: step.metadata,
      icon: 'server',
      time: step.start_time,
    });
  });

  (trace?.tool_calls || []).forEach((tool: any) => {
    events.push({
      kind: 'tool',
      title: `Tool call: ${tool.tool_name}`,
      detail: cleanPreview(tool.output_preview || tool.input) || 'A backend helper/tool was executed.',
      latency_ms: tool.latency_ms,
      status: tool.success ? 'success' : 'failed',
      metadata: tool,
      icon: 'tool',
      time: tool.logged_at,
    });
  });

  (trace?.llm_calls || []).forEach((llm: any) => {
    events.push({
      kind: 'llm',
      title: `LLM call: ${llm.model}`,
      detail: `${llm.provider} generated or routed text using ${fmtTokens(llm.total_tokens)} tokens at ${fmtCost(llm.cost_usd)}.`,
      latency_ms: llm.latency_ms,
      status: 'success',
      metadata: llm,
      icon: 'brain',
      time: llm.logged_at,
    });
  });

  (trace?.errors || []).forEach((err: any) => {
    events.push({
      kind: 'error',
      title: err.exception_type,
      detail: cleanPreview(err.message),
      latency_ms: 0,
      status: 'failed',
      metadata: err,
      icon: 'error',
      time: err.logged_at,
    });
  });

  events.push({
    kind: 'output',
    title: trace?.status === 'failed' ? 'Run ended with an error' : 'Final response returned',
    detail: cleanPreview(trace?.final_output?.summary_preview) || 'The backend completed the workflow and returned JSON to the app.',
    latency_ms: trace?.total_latency_ms,
    status: trace?.status,
    icon: 'spark',
    time: trace?.ended_at,
  });

  return events;
}

function explainStep(step: any) {
  const name = String(step?.step_name || '').toLowerCase();
  const meta = step?.metadata || {};
  if (name.includes('register uploaded file')) return 'MongoDB created a file record so this upload can be tracked later.';
  if (name.includes('save excel')) return `The uploaded spreadsheet was stored on disk${meta.file_size ? ` (${meta.file_size} bytes)` : ''}.`;
  if (name.includes('parse') || name.includes('read excel')) return `The Excel reader normalized columns and extracted ${meta.transaction_count || meta.records_count || 'the'} transactions.`;
  if (name.includes('timeline')) return `The holding ledger was built chronologically from buy/sell rows${meta.events_count ? ` (${meta.events_count} events)` : ''}.`;
  if (name.includes('supervisor')) return 'The routing layer decided which specialist agent should handle the request.';
  if (name.includes('portfolio')) return 'The portfolio agent calculated holdings, allocation, current value, and summary insights.';
  if (name.includes('p&l') || name.includes('pnl')) return 'The P&L agent calculated realized/unrealized profit, losses, and charges.';
  if (name.includes('dividend')) return 'The dividend agent checked corporate actions against the user holding dates.';
  if (name.includes('stock analysis')) return 'The stock analysis agent fetched market data, fundamentals, dividends, and yearly metrics.';
  if (name.includes('chat session')) return 'A chat session was created so later queries can attach to the uploaded file.';
  return 'A backend workflow step completed inside the request pipeline.';
}

function flowSummary(trace: any) {
  const selected = trace?.final_output?.agent_used || trace?.supervisor?.agent_selected || trace?.user_request?.selected_agent || 'unknown';
  const tools = trace?.tool_calls || [];
  const llms = trace?.llm_calls || [];
  if (!trace) return 'No trace selected yet.';
  if (selected === 'excel_reader_tool') {
    return 'Upload flow: FastAPI accepted the file, MongoDB registered it, the file was saved, the Excel reader normalized rows, and a chat session was created for future agent runs.';
  }
  return `Query flow: FastAPI received the message, the supervisor routed it to ${cleanAgent(selected)}, backend tools ran ${tools.length} time(s), LLM calls ran ${llms.length} time(s), and the final answer was saved with trace metrics.`;
}

function EventIcon({ type }: { type: string }) {
  if (type === 'file') return <Description style={iconStyle} />;
  if (type === 'message') return <ChatBubbleOutlined style={iconStyle} />;
  if (type === 'bot') return <SmartToy style={iconStyle} />;
  if (type === 'tool') return <Build style={iconStyle} />;
  if (type === 'brain') return <Psychology style={iconStyle} />;
  if (type === 'error') return <ReportProblem style={iconStyle} />;
  if (type === 'spark') return <AutoAwesome style={iconStyle} />;
  return <Storage style={iconStyle} />;
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="min-h-[260px] rounded-lg border border-white/10 bg-[#101010] flex flex-col items-center justify-center text-center px-6">
      <div className="w-10 h-10 rounded-lg bg-[#1baf7a]/10 text-[#1baf7a] flex items-center justify-center mb-3">
        <TimelineIcon style={{ fontSize: 18 }} />
      </div>
      <p className="text-sm font-semibold text-white">{title}</p>
      <p className="text-xs text-[#9ca3af] max-w-xl mt-2 leading-5">{body}</p>
    </div>
  );
}

function MetricTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-[#101010] p-4 min-h-24">
      <p className="text-[10px] uppercase tracking-wider text-[#8b949e] font-bold">{label}</p>
      <p className="text-2xl font-semibold text-white font-mono mt-3">{value}</p>
      {sub && <p className="text-xs text-[#8b949e] mt-1">{sub}</p>}
    </div>
  );
}

function TracePicker({
  traces,
  selectedTraceId,
  onSelect,
}: {
  traces: TraceSummary[];
  selectedTraceId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <select
      value={selectedTraceId || ''}
      onChange={(e) => onSelect(e.target.value)}
      className="w-full max-w-xl rounded-lg border border-white/10 bg-[#101010] px-3 py-2 text-xs text-white outline-none"
    >
      <option value="" disabled>
        Select a trace
      </option>
      {traces.map((trace) => (
        <option key={trace.trace_id} value={trace.trace_id}>
          {eventTime(trace.timestamp)} | {cleanAgent(trace.agent)} | {trace.query.slice(0, 70)}
        </option>
      ))}
    </select>
  );
}

export default function DeveloperDashboard() {
  const navigate = useNavigate();
  const [activePanel, setActivePanel] = useState<PanelKey>('trace');
  const [searchQuery, setSearchQuery] = useState('');
  const [refreshSeconds, setRefreshSeconds] = useState(5);
  const [liveSessions, setLiveSessions] = useState<any[]>([]);
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [selectedTraceId, setSelectedTraceId] = useState('');
  const [selectedTrace, setSelectedTrace] = useState<any>(null);
  const [agentStats, setAgentStats] = useState<any[]>([]);
  const [toolStats, setToolStats] = useState<any[]>([]);
  const [llmStats, setLlmStats] = useState<any[]>([]);
  const [errorStats, setErrorStats] = useState<any[]>([]);
  const [costStats, setCostStats] = useState<any>({});
  const [perfStats, setPerfStats] = useState<any>({});
  const [loading, setLoading] = useState(false);
  const [replayIndex, setReplayIndex] = useState(0);

  const filteredTraces = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return traces;
    return traces.filter((trace) =>
      trace.query.toLowerCase().includes(query) ||
      trace.trace_id.toLowerCase().includes(query) ||
      cleanAgent(trace.agent).toLowerCase().includes(query),
    );
  }, [searchQuery, traces]);

  const events = useMemo(() => buildEvents(selectedTrace), [selectedTrace]);
  async function openTrace(traceId: string) {
    if (!traceId) return;
    const res = await api.get(`/obs/traces/${traceId}`);
    setSelectedTrace(res.data);
    setSelectedTraceId(traceId);
    setReplayIndex(0);
  }

  async function fetchData(keepSelection = true) {
    setLoading(true);
    try {
      const [liveRes, histRes, agentsRes, toolsRes, llmRes, errorsRes, costRes, perfRes] = await Promise.all([
        api.get('/obs/live'),
        api.get('/obs/traces?page=1&page_size=30'),
        api.get('/obs/analytics/agents'),
        api.get('/obs/analytics/tools'),
        api.get('/obs/analytics/llm'),
        api.get('/obs/analytics/errors'),
        api.get('/obs/analytics/cost'),
        api.get('/obs/analytics/performance'),
      ]);

      setLiveSessions(liveRes.data.traces || []);
      const mapped = (histRes.data.traces || []).map((trace: any) => ({
        trace_id: trace.trace_id,
        timestamp: trace.created_at,
        query: trace.user_request?.original_prompt || 'Direct backend run',
        agent: trace.final_output?.agent_used || trace.supervisor?.agent_selected || trace.user_request?.selected_agent || 'unknown',
        status: trace.status === 'success' ? 'success' : trace.status === 'running' ? 'running' : 'failed',
        latency_ms: trace.total_latency_ms || trace.performance?.total_latency_ms || 0,
        total_tokens: trace.cost_analytics?.total_tokens || 0,
        cost_usd: trace.cost_analytics?.total_cost_usd || 0,
      }));
      setTraces(mapped);
      setAgentStats(agentsRes.data.agents || []);
      setToolStats(toolsRes.data.tools || []);
      setLlmStats(llmRes.data.models || []);
      setErrorStats(errorsRes.data.error_types || []);
      setCostStats(costRes.data || {});
      setPerfStats(perfRes.data || {});

      const shouldOpenFirst = mapped.length > 0 && (!keepSelection || !selectedTraceId);
      if (shouldOpenFirst) {
        await openTrace(mapped[0].trace_id);
      } else if (selectedTraceId) {
        await openTrace(selectedTraceId);
      }
    } catch (err) {
      console.error('Failed to load observability data', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchData(false);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => fetchData(true), refreshSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [refreshSeconds, selectedTraceId]);

  return (
    <div className="min-h-screen bg-[#070707] text-white flex flex-col">
      <header className="h-16 border-b border-white/10 bg-[#101010] px-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-sky-500 to-emerald-500 flex items-center justify-center text-sm font-bold">
            EI
          </div>
          <div>
            <h1 className="text-sm font-semibold">Equity Intelligence Developer Dashboard</h1>
            <p className="text-[11px] text-[#8b949e]">Backend flight recorder for uploads, agents, tools, LLM tokens, latency, and cost</p>
          </div>
          <span className="h-5 w-px bg-white/10" />
          <span className="flex items-center gap-2 text-xs text-[#9ca3af]">
            <span className={`h-2.5 w-2.5 rounded-full ${liveSessions.length ? 'bg-emerald-400 animate-pulse' : 'bg-[#6b7280]'}`} />
            {liveSessions.length} live sessions
          </span>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative">
            <Search style={{ fontSize: 15 }} className="absolute left-3 top-2.5 text-[#8b949e]" />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search traces, agents, queries..."
              className="w-64 rounded-lg border border-white/10 bg-[#070707] pl-9 pr-3 py-2 text-xs outline-none focus:border-emerald-500"
            />
          </div>
          <select
            value={refreshSeconds}
            onChange={(e) => setRefreshSeconds(Number(e.target.value))}
            className="rounded-lg border border-white/10 bg-[#070707] px-3 py-2 text-xs"
          >
            <option value={5}>5s refresh</option>
            <option value={10}>10s refresh</option>
            <option value={30}>30s refresh</option>
          </select>
          <button
            onClick={() => navigate('/')}
            className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/30 px-3 py-2 text-xs text-emerald-400 hover:bg-emerald-500/10"
          >
            <ArrowBack style={{ fontSize: 14 }} />
            Back to App
          </button>
        </div>
      </header>

      <div className="flex flex-1 min-h-0">
        <aside className="w-[148px] border-r border-white/10 bg-[#090909] py-4 shrink-0">
          {panels.map((panel) => (
            <button
              key={panel.key}
              onClick={() => setActivePanel(panel.key)}
              className={`w-full h-14 px-4 flex items-center gap-3 text-xs transition ${
                activePanel === panel.key
                  ? 'bg-[#101010] text-emerald-400 border-r-2 border-emerald-400'
                  : 'text-[#9ca3af] hover:bg-white/5 hover:text-white'
              }`}
            >
              {panel.icon}
              <span>{panel.label}</span>
            </button>
          ))}
        </aside>

        <main className="flex-1 overflow-y-auto p-7">
          {activePanel === 'live' && (
            <section className="space-y-6">
              <div>
                <h2 className="text-xl font-semibold">Live Backend Runs</h2>
                <p className="text-sm text-[#9ca3af] mt-1">Shows requests while they are actively executing. Completed runs move into History and Trace.</p>
              </div>
              {liveSessions.length === 0 ? (
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
                  <EmptyState
                    title="No active sessions right now"
                    body="This is normal when no upload or agent request is currently running. The latest completed backend run is still available below so the page never feels blank."
                  />
                  <TraceOverview trace={selectedTrace} />
                </div>
              ) : (
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  {liveSessions.map((trace) => (
                    <button
                      key={trace.trace_id}
                      onClick={() => openTrace(trace.trace_id)}
                      className="text-left rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-5 hover:bg-emerald-500/10"
                    >
                      <p className="text-xs text-emerald-400 font-semibold">Running now</p>
                      <p className="mt-2 text-sm font-semibold">{trace.user_request?.original_prompt || 'Backend workflow'}</p>
                      <p className="text-xs text-[#9ca3af] mt-2">{trace.workflow_steps?.at(-1)?.step_name || 'Initializing'}</p>
                    </button>
                  ))}
                </div>
              )}
            </section>
          )}

          {activePanel === 'history' && (
            <section className="space-y-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-xl font-semibold">Trace History</h2>
                  <p className="text-sm text-[#9ca3af] mt-1">Every upload, chat query, direct agent click, tool call, LLM call, and final response should land here.</p>
                </div>
                <button onClick={() => fetchData(false)} className="rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-black">
                  {loading ? 'Refreshing...' : 'Refresh now'}
                </button>
              </div>

              {filteredTraces.length === 0 ? (
                <EmptyState
                  title="No trace records found yet"
                  body="Upload an Excel file or ask a chat question. After the backend finishes, the run will appear here with agent, tools, tokens, latency, and cost."
                />
              ) : (
                <div className="rounded-lg border border-white/10 overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-[#101010] text-[10px] uppercase tracking-wider text-[#8b949e]">
                      <tr>
                        <th className="text-left p-3">Time</th>
                        <th className="text-left p-3">Request</th>
                        <th className="text-left p-3">Agent</th>
                        <th className="text-left p-3">Latency</th>
                        <th className="text-left p-3">Tokens</th>
                        <th className="text-left p-3">Cost</th>
                        <th className="text-left p-3">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredTraces.map((trace) => (
                        <tr
                          key={trace.trace_id}
                          onClick={() => {
                            openTrace(trace.trace_id);
                            setActivePanel('trace');
                          }}
                          className="border-t border-white/5 hover:bg-white/[0.03] cursor-pointer"
                        >
                          <td className="p-3 text-xs text-[#9ca3af]">{eventTime(trace.timestamp)}</td>
                          <td className="p-3 max-w-[520px] truncate">{trace.query}</td>
                          <td className="p-3">
                            <span className="rounded-full px-2 py-1 text-[11px]" style={{ backgroundColor: `${agentColors[trace.agent] || '#64748b'}22`, color: agentColors[trace.agent] || '#cbd5e1' }}>
                              {cleanAgent(trace.agent)}
                            </span>
                          </td>
                          <td className="p-3 font-mono text-xs">{fmtLatency(trace.latency_ms)}</td>
                          <td className="p-3 font-mono text-xs">{fmtTokens(trace.total_tokens)}</td>
                          <td className="p-3 font-mono text-xs">{fmtCost(trace.cost_usd)}</td>
                          <td className="p-3">
                            <span className={`text-[11px] font-semibold ${trace.status === 'success' ? 'text-emerald-400' : trace.status === 'running' ? 'text-sky-400' : 'text-red-400'}`}>
                              {trace.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}

          {activePanel === 'trace' && (
            <section className="space-y-6">
              <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-4">
                <div>
                  <h2 className="text-xl font-semibold">Trace Explorer</h2>
                  <p className="text-sm text-[#9ca3af] mt-1">Plain-English explanation of what the backend did for one upload or one chat query.</p>
                </div>
                <TracePicker traces={filteredTraces} selectedTraceId={selectedTraceId} onSelect={openTrace} />
              </div>

              {!selectedTrace ? (
                <EmptyState
                  title="Select or create a trace"
                  body="Once you upload Excel or ask an agent question, this screen will show the route, tools, token usage, latency, and final output as a readable backend story."
                />
              ) : (
                <>
                  <TraceOverview trace={selectedTrace} />
                  <div className="rounded-lg border border-white/10 bg-[#101010] p-5">
                    <p className="text-[10px] uppercase tracking-wider text-[#8b949e] font-bold">Internal Mechanism</p>
                    <p className="text-sm text-white leading-6 mt-3">{flowSummary(selectedTrace)}</p>
                  </div>
                  <Timeline events={events} />
                </>
              )}
            </section>
          )}

          {activePanel === 'tools' && (
            <StatsPanel
              title="Tool Calls"
              subtitle="Backend helpers used by agents: Excel parsing, storage, P&L calculator, dividend fetcher, market data, and similar tools."
              empty="No tool calls are recorded yet. Upload a sheet or run an agent to populate this."
              rows={toolStats.map((tool) => ({
                name: tool._id || 'Unknown tool',
                meta: `${tool.total_calls || 0} calls`,
                right: `${fmtLatency(tool.avg_latency_ms)} avg`,
                sub: `${tool.success_calls || 0} successful, ${tool.failed_calls || 0} failed`,
              }))}
            />
          )}

          {activePanel === 'llms' && (
            <StatsPanel
              title="LLM Calls"
              subtitle="Every model invocation with input tokens, output tokens, latency, and estimated cost."
              empty="No LLM calls are recorded yet. Run a chat query or agent report to populate this."
              rows={llmStats.map((model) => ({
                name: model._id || 'Unknown model',
                meta: `${model.total_calls || 0} calls`,
                right: fmtCost(model.total_cost_usd),
                sub: `${fmtTokens(model.total_tokens_in)} input tokens, ${fmtTokens(model.total_tokens_out)} output tokens, ${fmtLatency(model.avg_latency_ms)} avg latency`,
              }))}
            />
          )}

          {activePanel === 'agents' && (
            <StatsPanel
              title="Agent Routing"
              subtitle="Shows which specialist agent handled each backend run and how reliably it completed."
              empty="No agent runs are recorded yet."
              rows={agentStats.map((agent) => ({
                name: cleanAgent(agent._id || 'unknown'),
                meta: `${agent.count || 0} runs`,
                right: `${Math.round(((agent.success_count || 0) / (agent.count || 1)) * 100)}% success`,
                sub: `${fmtLatency(agent.avg_latency_ms)} average end-to-end latency`,
              }))}
            />
          )}

          {activePanel === 'errors' && (
            <StatsPanel
              title="Errors"
              subtitle="Failures grouped by exception type, so you can see which backend layer needs attention."
              empty="No errors recorded. Good sign."
              rows={errorStats.map((err) => ({
                name: err._id || 'Unknown error',
                meta: `${err.count || 0} occurrences`,
                right: eventTime(err.last_seen),
                sub: `Affected agents: ${(err.agents || []).map(cleanAgent).join(', ') || 'unknown'}`,
              }))}
            />
          )}

          {activePanel === 'cost' && (
            <section className="space-y-6">
              <div>
                <h2 className="text-xl font-semibold">Cost Breakdown</h2>
                <p className="text-sm text-[#9ca3af] mt-1">Estimated model cost from recorded LLM token usage.</p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <MetricTile label="Today" value={fmtCost(costStats.daily_cost_usd)} />
                <MetricTile label="This month" value={fmtCost(costStats.monthly_cost_usd)} />
                <MetricTile label="All time" value={fmtCost(costStats.total_cost_usd)} />
              </div>
              <StatsPanel
                title="Cost by Agent"
                subtitle="Which agent family is consuming the most LLM budget."
                empty="No cost data yet."
                rows={(costStats.per_agent || []).map((row: any) => ({
                  name: cleanAgent(row._id || 'unknown'),
                  meta: 'estimated LLM spend',
                  right: fmtCost(row.cost_usd),
                  sub: 'Tool calls are shown in latency, but cost is only estimated for LLM calls.',
                }))}
              />
            </section>
          )}

          {activePanel === 'perf' && (
            <section className="space-y-6">
              <div>
                <h2 className="text-xl font-semibold">Performance</h2>
                <p className="text-sm text-[#9ca3af] mt-1">Where time is spent: total request time, LLM time, tool time, and database time.</p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <MetricTile label="Average total" value={fmtLatency(perfStats.avg_total_latency_ms)} />
                <MetricTile label="Average LLM" value={fmtLatency(perfStats.avg_llm_latency_ms)} />
                <MetricTile label="Average tools" value={fmtLatency(perfStats.avg_tool_latency_ms)} />
                <MetricTile label="Average DB" value={fmtLatency(perfStats.avg_db_latency_ms)} />
              </div>
              <Timeline events={events} />
            </section>
          )}

          {activePanel === 'replay' && (
            <section className="space-y-6">
              <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-4">
                <div>
                  <h2 className="text-xl font-semibold">Execution Replay</h2>
                  <p className="text-sm text-[#9ca3af] mt-1">Step through a completed backend run in order.</p>
                </div>
                <TracePicker traces={filteredTraces} selectedTraceId={selectedTraceId} onSelect={openTrace} />
              </div>
              {!selectedTrace ? (
                <EmptyState title="No replay available yet" body="Run an upload or agent query first, then this screen will replay every recorded backend event." />
              ) : (
                <div className="rounded-lg border border-white/10 bg-[#101010] p-5 space-y-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-[#8b949e] font-bold">Replay position</p>
                      <p className="text-sm text-white mt-1">Step {Math.min(replayIndex + 1, events.length)} of {events.length}</p>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setReplayIndex((idx) => Math.max(0, idx - 1))}
                        className="rounded-lg border border-white/10 px-3 py-2 text-xs text-[#d1d5db]"
                      >
                        Previous
                      </button>
                      <button
                        onClick={() => setReplayIndex((idx) => Math.min(events.length - 1, idx + 1))}
                        className="rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-black"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                  <div className="h-2 rounded-full bg-black overflow-hidden">
                    <div className="h-full bg-emerald-500" style={{ width: `${((replayIndex + 1) / Math.max(events.length, 1)) * 100}%` }} />
                  </div>
                  <Timeline events={events.slice(0, replayIndex + 1)} />
                </div>
              )}
            </section>
          )}
        </main>
      </div>
    </div>
  );
}

function TraceOverview({ trace }: { trace: any }) {
  if (!trace) {
    return <EmptyState title="No latest trace available" body="Upload a file or run a query and this panel will summarize the newest backend execution." />;
  }
  const agent = trace.final_output?.agent_used || trace.supervisor?.agent_selected || trace.user_request?.selected_agent || 'unknown';
  const tools = trace.tool_calls?.length || 0;
  const llms = trace.llm_calls?.length || 0;
  return (
    <div className="rounded-lg border border-white/10 bg-[#101010] p-5 space-y-5">
      <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-4">
        <div>
          <p className="text-[10px] uppercase tracking-wider text-[#8b949e] font-bold">Selected run</p>
          <h3 className="text-lg font-semibold mt-2">{trace.user_request?.original_prompt || 'Backend workflow'}</h3>
          <p className="text-sm text-[#9ca3af] mt-2 leading-6">{cleanPreview(trace.final_output?.summary_preview) || flowSummary(trace)}</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${trace.status === 'success' ? 'bg-emerald-500/10 text-emerald-400' : trace.status === 'running' ? 'bg-sky-500/10 text-sky-400' : 'bg-red-500/10 text-red-400'}`}>
          {trace.status}
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <MetricTile label="Activated agent" value={cleanAgent(agent)} sub="who handled it" />
        <MetricTile label="Total latency" value={fmtLatency(trace.total_latency_ms)} sub="end-to-end" />
        <MetricTile label="Tool calls" value={`${tools}`} sub="backend helpers" />
        <MetricTile label="LLM calls" value={`${llms}`} sub={`${fmtTokens(trace.cost_analytics?.total_tokens)} tokens`} />
        <MetricTile label="Cost" value={fmtCost(trace.cost_analytics?.total_cost_usd)} sub="estimated LLM cost" />
      </div>
    </div>
  );
}

function Timeline({ events }: { events: any[] }) {
  return (
    <div className="rounded-lg border border-white/10 bg-[#101010] p-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-wider text-[#8b949e] font-bold">Execution Timeline</p>
          <p className="text-sm text-[#9ca3af] mt-1">Readable step-by-step backend mechanism</p>
        </div>
        <p className="text-xs text-[#8b949e]">{events.length} events</p>
      </div>
      <div className="mt-6 space-y-4">
        {events.map((event, index) => (
          <div key={`${event.kind}-${index}`} className="grid grid-cols-[34px_1fr] gap-4">
            <div className="flex flex-col items-center">
              <div className={`h-8 w-8 rounded-lg flex items-center justify-center ${
                event.status === 'failed' ? 'bg-red-500/10 text-red-400' : event.kind === 'llm' ? 'bg-purple-500/10 text-purple-300' : event.kind === 'tool' ? 'bg-amber-500/10 text-amber-300' : 'bg-emerald-500/10 text-emerald-400'
              }`}>
                <EventIcon type={event.icon} />
              </div>
              {index < events.length - 1 && <div className="w-px flex-1 min-h-8 bg-white/10 mt-2" />}
            </div>
            <div className="rounded-lg border border-white/10 bg-black/30 p-4">
              <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-white">{event.title}</p>
                  <p className="text-xs text-[#9ca3af] leading-5 mt-1">{event.detail}</p>
                </div>
                <div className="flex items-center gap-3 text-[11px] text-[#8b949e] shrink-0">
                  {event.time && <span>{eventTime(event.time)}</span>}
                  <span className="inline-flex items-center gap-1"><AccessTime style={{ fontSize: 12 }} />{fmtLatency(event.latency_ms)}</span>
                </div>
              </div>
              {event.kind === 'llm' && event.metadata && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4 text-xs">
                  <Mini label="Input" value={fmtTokens(event.metadata.tokens_in)} />
                  <Mini label="Output" value={fmtTokens(event.metadata.tokens_out)} />
                  <Mini label="Total" value={fmtTokens(event.metadata.total_tokens)} />
                  <Mini label="Cost" value={fmtCost(event.metadata.cost_usd)} />
                </div>
              )}
              {event.kind === 'tool' && event.metadata && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4 text-xs">
                  <Mini label="Tool type" value={event.metadata.tool_type || 'python'} />
                  <Mini label="Retry count" value={`${event.metadata.retry_count || 0}`} />
                  <Mini label="Status" value={event.metadata.success ? 'success' : 'failed'} />
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-[#101010] border border-white/10 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wider text-[#8b949e]">{label}</p>
      <p className="text-white font-mono mt-1">{value}</p>
    </div>
  );
}

function StatsPanel({
  title,
  subtitle,
  empty,
  rows,
}: {
  title: string;
  subtitle: string;
  empty: string;
  rows: Array<{ name: string; meta: string; right: string; sub: string }>;
}) {
  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">{title}</h2>
        <p className="text-sm text-[#9ca3af] mt-1">{subtitle}</p>
      </div>
      {rows.length === 0 ? (
        <EmptyState title={empty} body="The dashboard is waiting for trace data from the backend tracer. Run a real upload or agent query to populate this panel." />
      ) : (
        <div className="space-y-3">
          {rows.map((row, index) => (
            <div key={`${row.name}-${index}`} className="rounded-lg border border-white/10 bg-[#101010] p-4 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-white">{row.name}</p>
                <p className="text-xs text-[#9ca3af] mt-1">{row.sub}</p>
              </div>
              <div className="text-left md:text-right">
                <p className="text-sm font-mono text-white">{row.right}</p>
                <p className="text-xs text-[#8b949e] mt-1">{row.meta}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
