import { useCallback } from 'react';
import { useAppStore, type KPI, type Step, type Message } from '../store/appStore';

const API_BASE = '/api/v1';

interface AgentResponse {
  success: boolean;
  execution_time: number;
  agent_used: string | null;
  agent_plan: string | null;
  summary: string;
  insights: string[];
  structured_data: Record<string, unknown>;
}

function parseReActSteps(agentPlan: string | null): Step[] {
  if (!agentPlan) return [];
  const steps: Step[] = [];
  const lines = agentPlan.split('\n');
  let currentStep = 1;
  let currentThought = '';
  let currentAction = '';
  let currentInput = '';
  let currentObs = '';

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('Thought:')) {
      if (currentThought || currentAction || currentObs) {
        steps.push({
          step_num: currentStep,
          thought: currentThought || undefined,
          action: currentAction || undefined,
          tool_input: currentInput || undefined,
          observation: currentObs || undefined,
        });
        currentStep++;
        currentThought = '';
        currentAction = '';
        currentInput = '';
        currentObs = '';
      }
      currentThought = trimmed.replace('Thought:', '').trim();
    } else if (trimmed.startsWith('Action:')) {
      currentAction = trimmed.replace('Action:', '').trim();
    } else if (trimmed.startsWith('Action Input:')) {
      currentInput = trimmed.replace('Action Input:', '').trim();
    } else if (trimmed.startsWith('Observation:')) {
      currentObs = trimmed.replace('Observation:', '').trim();
    }
  }

  if (currentThought || currentAction || currentObs) {
    steps.push({
      step_num: currentStep,
      thought: currentThought || undefined,
      action: currentAction || undefined,
      tool_input: currentInput || undefined,
      observation: currentObs || undefined,
    });
  }

  return steps;
}

function extractKPIsFromStructuredData(data: Record<string, unknown>, agentUsed: string | null): KPI[] {
  const kpis: KPI[] = [];

  if (agentUsed === 'pnl_agent' || agentUsed === 'portfolio_agent') {
    const sd = data as Record<string, Record<string, unknown>>;
    if (sd.portfolio_summary) {
      const ps = sd.portfolio_summary;
      if (ps.total_invested != null) {
        kpis.push({ label: 'Total Invested', value: `₹${Number(ps.total_invested).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`, type: 'neutral' });
      }
      if (ps.total_realised_pnl != null) {
        const val = Number(ps.total_realised_pnl);
        kpis.push({ label: 'Realised P&L', value: `₹${Math.abs(val).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`, type: val >= 0 ? 'gain' : 'loss' });
      }
      if (ps.total_current_value != null) {
        kpis.push({ label: 'Current Value', value: `₹${Number(ps.total_current_value).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`, type: 'neutral' });
      }
      if (ps.total_charges != null) {
        kpis.push({ label: 'Total Charges', value: `₹${Number(ps.total_charges).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`, type: 'loss' });
      }
    }
  }

  if (agentUsed === 'dividend_agent') {
    const sd = data as Record<string, unknown>;
    if (sd.total_received != null) {
      kpis.push({ label: 'Dividends Received', value: `₹${Number(sd.total_received).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`, type: 'gain' });
    }
    if (sd.total_missed != null) {
      kpis.push({ label: 'Dividends Missed', value: `₹${Number(sd.total_missed).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`, type: 'loss' });
    }
    if (sd.yield_on_cost != null) {
      kpis.push({ label: 'Yield on Cost', value: `${Number(sd.yield_on_cost).toFixed(2)}%`, type: 'neutral' });
    }
  }

  if (agentUsed === 'stock_analysis_agent') {
    const sd = data as Record<string, unknown>;
    if (sd.fundamentals) {
      const fund = sd.fundamentals as Record<string, unknown>;
      if (fund.market_cap != null) {
        const mc = Number(fund.market_cap);
        const mcStr = mc >= 1e12 
          ? `₹${(mc / 1e12).toFixed(2)}T` 
          : `₹${(mc / 1e7).toLocaleString('en-IN', { maximumFractionDigits: 0 })}Cr`;
        kpis.push({ label: 'Market Cap', value: mcStr, type: 'neutral' });
      }
      if (fund.pe_ratio != null) {
        kpis.push({ label: 'P/E Ratio', value: `${Number(fund.pe_ratio).toFixed(1)}x`, type: 'neutral' });
      }
      if (fund.dividend_yield != null) {
        kpis.push({ label: 'Div Yield', value: `${Number(fund.dividend_yield).toFixed(2)}%`, type: 'neutral' });
      }
    }
  }

  return kpis;
}

export function useAgentCall() {
  const store = useAppStore();

  const callAgent = useCallback(async (message?: string) => {
    const { selectedAgent } = useAppStore.getState();

    store.clearRun();
    store.setStreaming(true);

    // Create AbortController for request cancellation
    const controller = new AbortController();
    store.setAbort(() => {
      controller.abort();
    });

    // Add user message
    if (message) {
      const userMsg: Message = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: message,
        timestamp: Date.now(),
      };
      store.addMessage(userMsg);
    }

    // Add placeholder agent message
    const agentMsgId = `agent-${Date.now()}`;
    const placeholderMsg: Message = {
      id: agentMsgId,
      role: 'agent',
      content: '',
      timestamp: Date.now(),
    };
    store.addMessage(placeholderMsg);

    try {
      let url: string;
      let options: RequestInit;

      const token = localStorage.getItem('access_token');
      const authHeaders: Record<string, string> = {};
      if (token) {
        authHeaders['Authorization'] = `Bearer ${token}`;
      }

      const activeSession = store.activeSessionId;

      if (selectedAgent === 'auto' && message) {
        url = `${API_BASE}/chat`;
        options = {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            ...authHeaders
          },
          body: JSON.stringify({ message, session_id: activeSession }),
          signal: controller.signal,
        };
      } else if (selectedAgent === 'stock_analysis') {
        url = `${API_BASE}/agent/stock_analysis`;
        options = {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            ...authHeaders
          },
          body: JSON.stringify({ message: message || 'Analyze TCS for 2024', session_id: activeSession }),
          signal: controller.signal,
        };
      } else {
        const agentMap: Record<string, string> = {
          portfolio: 'portfolio',
          pnl: 'pnl',
          dividend: 'dividend',
        };
        const endpoint = agentMap[selectedAgent] || 'portfolio';
        url = `${API_BASE}/agent/${endpoint}${activeSession ? `?session_id=${activeSession}` : ''}`;
        options = { 
          method: 'POST',
          headers: {
            ...authHeaders
          },
          signal: controller.signal,
        };
      }

      const res = await fetch(url, options);
      const data: AgentResponse = await res.json();

      // Parse ReAct steps from agent_plan
      const steps = parseReActSteps(data.agent_plan);
      store.setSteps(steps);

      // Extract KPIs
      const kpis = extractKPIsFromStructuredData(data.structured_data, data.agent_used);
      store.setKPIs(kpis);

      // Extract tables from structured_data
      const sd = data.structured_data as Record<string, unknown>;
      if (sd.open_positions && Array.isArray(sd.open_positions)) {
        store.setTableRows('open', sd.open_positions as Record<string, unknown>[]);
      }
      if (sd.realised_trades && Array.isArray(sd.realised_trades)) {
        store.setTableRows('realised', sd.realised_trades as Record<string, unknown>[]);
      }
      if (sd.charges_breakdown && Array.isArray(sd.charges_breakdown)) {
        store.setTableRows('charges', sd.charges_breakdown as Record<string, unknown>[]);
      }
      if (sd.trades && Array.isArray(sd.trades)) {
        store.setTableRows('trades', sd.trades as Record<string, unknown>[]);
      }

      // Update agent message
      const updatedMsg: Message = {
        id: agentMsgId,
        role: 'agent',
        content: data.summary || 'Analysis complete.',
        agentUsed: data.agent_used || undefined,
        confidence: 'high',
        routed: selectedAgent === 'auto',
        kpis,
        steps,
        structuredData: data.structured_data,
        insights: data.insights,
        executionTime: data.execution_time,
        timestamp: Date.now(),
      };

      // Replace last message
      const msgs = useAppStore.getState().messages.map((m) =>
        m.id === agentMsgId ? updatedMsg : m
      );
      useAppStore.setState({ messages: msgs, lastRoute: { agent: data.agent_used || '', confidence: 'high' } });
    } catch (err) {
      // Check if this is an AbortError from cancellation
      if (err instanceof Error && err.name === 'AbortError') {
        const cancelledMsg: Message = {
          id: agentMsgId,
          role: 'agent',
          content: '⚠️ Analysis stopped by user.',
          timestamp: Date.now(),
        };
        const msgs = useAppStore.getState().messages.map((m) =>
          m.id === agentMsgId ? cancelledMsg : m
        );
        useAppStore.setState({ messages: msgs });
        return;
      }

      const errorMsg: Message = {
        id: agentMsgId,
        role: 'agent',
        content: `Something went wrong: ${err instanceof Error ? err.message : 'Unknown error'}. Try again.`,
        timestamp: Date.now(),
      };
      const msgs = useAppStore.getState().messages.map((m) =>
        m.id === agentMsgId ? errorMsg : m
      );
      useAppStore.setState({ messages: msgs });
    } finally {
      store.setAbort(null);
      store.setStreaming(false);
    }
  }, [store]);

  return { callAgent };
}
