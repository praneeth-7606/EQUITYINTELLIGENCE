import { useNavigate } from 'react-router-dom';

import { useAppStore, type Tab } from '../../store/appStore';

const navigation: Array<{ id: Tab | 'statements'; label: string; hint: string; short: string }> = [
  { id: 'chat', label: 'Chat', hint: 'Ask portfolio questions', short: 'CH' },
  { id: 'dashboard', label: 'Dashboard', hint: 'Metrics and visuals', short: 'DB' },
  { id: 'raw', label: 'Raw data', hint: 'Rows and mappings', short: 'RD' },
  { id: 'statements', label: 'Statements', hint: 'Uploads and history', short: 'ST' },
];

function maskIdentifier(value?: string | null) {
  const text = (value || '').trim();
  if (!text) return 'Protected';
  if (text.length <= 4) return '****';
  return `${text.slice(0, 2)}${'*'.repeat(Math.max(4, text.length - 4))}${text.slice(-2)}`;
}

function formatRange(startDate?: string, endDate?: string) {
  if (!startDate && !endDate) return 'Available after upload';
  if (startDate && endDate) return `${startDate} to ${endDate}`;
  return startDate || endDate || 'Available after upload';
}

function formatAgent(agent?: string) {
  if (!agent) return 'Awaiting first question';
  return agent
    .replace('_agent', '')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function Sidebar() {
  const navigate = useNavigate();
  const {
    reset,
    symbols,
    rowCount,
    columns,
    startDate,
    endDate,
    clientCode,
    messages,
    isStreaming,
    activeTab,
    setActiveTab,
  } = useAppStore();

  const latestAgentMessage = [...messages].reverse().find((message) => message.role === 'agent');

  return (
    <aside className="hidden w-[292px] shrink-0 border-r border-white/10 bg-[#090f17] xl:flex xl:flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        <nav className="rounded-lg border border-white/8 bg-[#101824] p-2">
          <p className="px-3 pb-2 pt-2 text-[10px] font-semibold uppercase tracking-[0.22em] text-[#8fa1af]">
            Navigation
          </p>
          <div className="space-y-1">
            {navigation.map((item) => {
              const active = item.id !== 'statements' && activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    if (item.id === 'statements') {
                      window.dispatchEvent(new Event('equity:open-statements'));
                    } else {
                      setActiveTab(item.id);
                    }
                  }}
                  className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition ${
                    active
                      ? 'bg-[#123145] text-white shadow-[inset_3px_0_0_#38bdf8]'
                      : 'text-[#c7d2da] hover:bg-white/[0.05]'
                  }`}
                >
                  <span
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[10px] font-bold ${
                      active ? 'bg-sky-400/15 text-sky-200' : 'bg-[#0a1119] text-[#8fa1af]'
                    }`}
                  >
                    {item.short}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold">{item.label}</span>
                    <span className="mt-0.5 block truncate text-[11px] text-[#8fa1af]">{item.hint}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </nav>

        <section className="overflow-hidden rounded-lg border border-[#d4a84c]/20 bg-[#101824]">
          <div className="border-b border-white/8 bg-[#d4a84c]/[0.07] px-5 py-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[#cdb477]">
                  Active statement
                </p>
                <h2 className="mt-2 font-display text-xl leading-tight text-[#f6f1e8]">
                  Portfolio workspace
                </h2>
              </div>
              <span
                className="h-2.5 w-2.5 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.6)]"
                title="Statement ready"
              />
            </div>
          </div>

          <div className="space-y-4 p-5 text-sm text-[#d7cec0]">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-md border border-white/8 bg-[#0a1119] p-3">
                <p className="text-[10px] uppercase tracking-[0.18em] text-[#8fa1af]">Rows</p>
                <p className="mt-2 text-lg font-semibold text-white">{rowCount || 0}</p>
              </div>
              <div className="rounded-md border border-white/8 bg-[#0a1119] p-3">
                <p className="text-[10px] uppercase tracking-[0.18em] text-[#8fa1af]">Stocks</p>
                <p className="mt-2 text-lg font-semibold text-white">{symbols.length}</p>
              </div>
            </div>

            <div>
              <p className="text-[10px] uppercase tracking-[0.18em] text-[#8fa1af]">Statement period</p>
              <p className="mt-1.5 leading-5">{formatRange(startDate, endDate)}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-[0.18em] text-[#8fa1af]">Privacy shield</p>
              <p className="mt-1.5 leading-5">
                {maskIdentifier(clientCode)} | {columns.length} mapped columns
              </p>
            </div>
          </div>
        </section>

        <section className="rounded-lg border border-white/8 bg-[#101824] p-5">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[#8fa1af]">
              Analysis engine
            </p>
            <span
              className={`rounded-full px-2 py-1 text-[10px] font-semibold ${
                isStreaming ? 'bg-amber-300/10 text-amber-200' : 'bg-emerald-400/10 text-emerald-300'
              }`}
            >
              {isStreaming ? 'Working' : 'Ready'}
            </span>
          </div>
          <div className="mt-4 flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-[#0d2e32] text-xs font-bold text-[#70e4dc]">
              AI
            </div>
            <div>
              <p className="text-sm font-semibold text-white">Smart routing enabled</p>
              <p className="mt-1 text-xs leading-5 text-[#8fa1af]">
                Each question is sent to the appropriate specialist automatically.
              </p>
            </div>
          </div>
        </section>

        <section className="rounded-lg border border-white/8 bg-[#101824] p-5">
          <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[#8fa1af]">
            Latest response
          </p>
          {latestAgentMessage ? (
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-md border border-white/8 bg-[#0a1119] p-3">
                <p className="text-[10px] uppercase tracking-[0.16em] text-[#8fa1af]">Specialist</p>
                <p className="mt-2 text-xs font-semibold leading-5 text-white">
                  {formatAgent(latestAgentMessage.agentUsed)}
                </p>
              </div>
              <div className="rounded-md border border-white/8 bg-[#0a1119] p-3">
                <p className="text-[10px] uppercase tracking-[0.16em] text-[#8fa1af]">Delivery</p>
                <p className="mt-2 text-xs font-semibold leading-5 text-white">
                  {latestAgentMessage.executionTime != null
                    ? `${latestAgentMessage.executionTime.toFixed(2)}s`
                    : 'Pending'}
                </p>
              </div>
            </div>
          ) : (
            <p className="mt-3 text-sm leading-6 text-[#8fa1af]">
              The responding specialist and delivery time will appear here.
            </p>
          )}
        </section>

        <section className="rounded-lg border border-white/8 bg-[#101824] p-5">
          <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[#8fa1af]">
            Workspace
          </p>
          <div className="mt-4 space-y-2.5">
            <button
              onClick={() => navigate('/developer')}
              className="w-full rounded-md border border-[#0ea5a4]/28 bg-[#0ea5a4]/10 px-4 py-3 text-left text-sm font-semibold text-[#9bf4ef] transition hover:bg-[#0ea5a4]/15"
            >
              Developer dashboard
            </button>
            <button
              onClick={reset}
              className="w-full rounded-md border border-white/10 bg-white/5 px-4 py-3 text-left text-sm font-semibold text-white transition hover:bg-white/10"
            >
              Start new upload
            </button>
          </div>
        </section>
      </div>
    </aside>
  );
}
