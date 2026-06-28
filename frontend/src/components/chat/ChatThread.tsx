import { useRef, useEffect, useCallback } from 'react';

import { useAppStore, type Message } from '../../store/appStore';
import AgentBadge from './AgentBadge';
import ReActLogPanel from './ReActLogPanel';
import { useAgentCall } from '../../hooks/useSSEStream';
import MarkdownRenderer from './MarkdownRenderer';

function UserMessage({ msg }: { msg: Message }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[72%] rounded-2xl rounded-br-md border border-[#d4a84c]/14 bg-[linear-gradient(180deg,_rgba(212,168,76,0.14),_rgba(212,168,76,0.06))] px-4 py-3 text-[#f6f1e8]">
        <MarkdownRenderer content={msg.content} />
      </div>
    </div>
  );
}

function AgentMessage({ msg, isStreaming }: { msg: Message; isStreaming: boolean }) {
  const showLoading = isStreaming && !msg.content;

  return (
    <div className="flex justify-start">
      <div className="max-w-[88%] space-y-2">
        {msg.agentUsed && (
          <AgentBadge
            agentUsed={msg.agentUsed}
            confidence={msg.confidence}
            routed={msg.routed}
          />
        )}

        <div className="rounded-2xl rounded-bl-md border border-white/8 bg-[linear-gradient(180deg,_rgba(255,255,255,0.035),_rgba(255,255,255,0.018))] px-4 py-3">
          {showLoading ? (
            <div className="flex items-center gap-2">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-[#d4a84c] border-t-transparent" />
              <span className="text-sm text-[#b8ab94]">Analyzing statement and routing the best backend path...</span>
            </div>
          ) : (
            <div className="space-y-3">
              <MarkdownRenderer content={msg.content} />

              {msg.kpis && msg.kpis.length > 0 && (
                <div className="flex flex-wrap gap-3 border-t border-border/50 pt-2">
                  {msg.kpis.map((kpi, i) => (
                    <div key={i} className="min-w-[120px] rounded-lg bg-canvas/50 px-3 py-2">
                      <p className="label text-[9px]">{kpi.label}</p>
                      <p
                        className={`font-display text-lg ${
                          kpi.type === 'gain'
                            ? 'text-gain'
                            : kpi.type === 'loss'
                              ? 'text-loss'
                              : 'text-text'
                        }`}
                      >
                        {kpi.value}
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {msg.insights && msg.insights.length > 0 && (
                <div className="space-y-1 border-t border-border/50 pt-2">
                  <p className="label text-[9px]">Insights</p>
                  {msg.insights.map((ins, i) => (
                    <p key={i} className="text-xs leading-relaxed text-muted">- {ins}</p>
                  ))}
                </div>
              )}

              {msg.executionTime != null && (
                <div className="border-t border-border/50 pt-2">
                  <p className="text-[11px] text-[#b8ab94]">
                    Delivered in <span className="font-semibold text-[#f2d18a]">{msg.executionTime.toFixed(2)}s</span>
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {msg.steps && <ReActLogPanel steps={msg.steps} />}
      </div>
    </div>
  );
}

export default function ChatThread() {
  const { messages, isStreaming, setSelectedAgent } = useAppStore();
  const { callAgent } = useAgentCall();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSuggestion = useCallback((agent: 'portfolio' | 'pnl' | 'dividend') => {
    if (isStreaming) return;
    setSelectedAgent(agent);
    setTimeout(() => {
      callAgent();
      setTimeout(() => {
        setSelectedAgent('auto');
      }, 500);
    }, 50);
  }, [isStreaming, setSelectedAgent, callAgent]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="max-w-2xl space-y-6 text-center">
          <div className="space-y-3">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-3xl border border-[#d4a84c]/20 bg-[radial-gradient(circle,_rgba(212,168,76,0.24),_rgba(15,23,42,0.2))] text-2xl font-semibold text-[#f2d18a] shadow-[0_0_30px_rgba(181,140,63,0.15)]">
              EI
            </div>
            <h2 className="text-2xl font-semibold text-[#f6f1e8]">Premium stock intelligence for statements and single-stock research</h2>
            <p className="mx-auto max-w-xl text-sm leading-relaxed text-muted">
              Ask about portfolio structure, profit and loss, dividend intelligence, or use the stock-analysis path for direct company research with tracked latency and execution flow.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <button
              onClick={() => handleSuggestion('portfolio')}
              className="group rounded-2xl border border-[#d4a84c]/12 bg-[linear-gradient(180deg,_rgba(255,255,255,0.04),_rgba(255,255,255,0.02))] p-4 text-center transition-all hover:border-[#d4a84c]/32 hover:shadow-[0_0_30px_rgba(181,140,63,0.08)]"
            >
              <div className="mb-1 text-xl transition-transform group-hover:scale-110">PI</div>
              <h3 className="text-xs font-semibold text-text transition-colors group-hover:text-[#f2d18a]">Portfolio Agent</h3>
              <p className="mt-1 text-[10px] leading-normal text-muted">
                Analyze concentration, holding patterns, and statement-level structure.
              </p>
            </button>

            <button
              onClick={() => handleSuggestion('pnl')}
              className="group rounded-2xl border border-[#d4a84c]/12 bg-[linear-gradient(180deg,_rgba(255,255,255,0.04),_rgba(255,255,255,0.02))] p-4 text-center transition-all hover:border-[#d4a84c]/32 hover:shadow-[0_0_30px_rgba(181,140,63,0.08)]"
            >
              <div className="mb-1 text-xl transition-transform group-hover:scale-110">PL</div>
              <h3 className="text-xs font-semibold text-text transition-colors group-hover:text-[#f2d18a]">P&L Agent</h3>
              <p className="mt-1 text-[10px] leading-normal text-muted">
                Break down realized results, unrealized exposure, and charges.
              </p>
            </button>

            <button
              onClick={() => handleSuggestion('dividend')}
              className="group rounded-2xl border border-[#d4a84c]/12 bg-[linear-gradient(180deg,_rgba(255,255,255,0.04),_rgba(255,255,255,0.02))] p-4 text-center transition-all hover:border-[#d4a84c]/32 hover:shadow-[0_0_30px_rgba(181,140,63,0.08)]"
            >
              <div className="mb-1 text-xl transition-transform group-hover:scale-110">DI</div>
              <h3 className="text-xs font-semibold text-text transition-colors group-hover:text-[#f2d18a]">Dividend Agent</h3>
              <p className="mt-1 text-[10px] leading-normal text-muted">
                Review payouts, missed opportunities, and projected dividend income.
              </p>
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 space-y-4 overflow-y-auto p-5">
      {messages.map((msg, i) => (
        msg.role === 'user'
          ? <UserMessage key={msg.id} msg={msg} />
          : <AgentMessage key={msg.id} msg={msg} isStreaming={isStreaming && i === messages.length - 1} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
