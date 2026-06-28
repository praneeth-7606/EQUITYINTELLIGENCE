import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useAppStore } from '../../store/appStore';
import { useAuth } from '../../auth/AuthContext';

type SessionRecord = {
  _id: string;
  original_filename?: string;
  created_at?: string;
  conversation_name?: string;
};

type SessionMessage = {
  id: string;
  role: 'user' | 'agent';
  content: string;
  agentUsed?: string;
  timestamp: number;
};

function maskIdentifier(value?: string | null) {
  const text = (value || '').trim();
  if (!text) return '';
  if (text.length <= 4) return '****';
  return `${text.slice(0, 2)}${'*'.repeat(Math.max(4, text.length - 4))}${text.slice(-2)}`;
}

function maskEmail(email?: string | null) {
  const text = (email || '').trim();
  if (!text.includes('@')) return maskIdentifier(text);
  const [name, domain] = text.split('@');
  return `${name.slice(0, 2)}***@${domain}`;
}

function maskStatementLabel(label?: string | null) {
  const text = (label || '').trim();
  if (!text) return 'Protected statement';
  const extIndex = text.lastIndexOf('.');
  const ext = extIndex >= 0 ? text.slice(extIndex).toLowerCase() : '';
  return `Protected statement${ext}`;
}

function maskFreeText(text?: string | null) {
  return (text || '')
    .replace(/\b[A-Z]{5}\d{4}[A-Z]\b/gi, '<masked-pan>')
    .replace(/\b\d{8,}\b/g, '<masked-id>')
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, '<masked-email>')
    .replace(/(client\s*name\s*[:=-]\s*)([^\n,]+)/gi, '$1<masked-client>')
    .replace(/(client\s*code\s*[:=-]\s*)([^\n,]+)/gi, '$1<masked-code>');
}

export default function Topbar() {
  const { clientName, clientCode, uploaded, reset, activeSessionId, loadSessionHistory } = useAppStore();
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedSessionId, setExpandedSessionId] = useState<string | null>(null);
  const [sessionMessages, setSessionMessages] = useState<Record<string, SessionMessage[]>>({});
  const [historyLoadingId, setHistoryLoadingId] = useState<string | null>(null);

  const fetchSessions = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const headers: Record<string, string> = {};
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
      const res = await fetch('/api/v1/user/sessions', { headers });
      const data = await res.json();
      if (data.success) {
        setSessions(data.sessions || []);
      }
    } catch (err) {
      console.error('Error fetching sessions:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchSessionHistoryPreview = async (sessionId: string) => {
    if (sessionMessages[sessionId]) {
      return;
    }
    setHistoryLoadingId(sessionId);
    try {
      const token = localStorage.getItem('access_token');
      const headers: Record<string, string> = {};
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
      const res = await fetch(`/api/v1/chat/history/${sessionId}`, { headers });
      const data = await res.json();
      if (data.success && Array.isArray(data.messages)) {
        setSessionMessages((prev) => ({ ...prev, [sessionId]: data.messages }));
      } else {
        setSessionMessages((prev) => ({ ...prev, [sessionId]: [] }));
      }
    } catch (err) {
      console.error('Error fetching session history preview:', err);
      setSessionMessages((prev) => ({ ...prev, [sessionId]: [] }));
    } finally {
      setHistoryLoadingId(null);
    }
  };

  useEffect(() => {
    if (isDrawerOpen) {
      fetchSessions();
    }
  }, [isDrawerOpen]);

  useEffect(() => {
    const openDrawer = () => setIsDrawerOpen(true);
    window.addEventListener('equity:open-statements', openDrawer);
    return () => window.removeEventListener('equity:open-statements', openDrawer);
  }, []);

  const handleActivateSession = async (sessionId: string) => {
    await loadSessionHistory(sessionId);
    setIsDrawerOpen(false);
  };

  const handleDeleteSession = async (sessionId: string) => {
    if (!window.confirm('Are you sure you want to delete this statement session? This will remove its chat history and trace logs.')) {
      return;
    }
    try {
      const token = localStorage.getItem('access_token');
      const headers: Record<string, string> = {};
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
      const res = await fetch(`/api/v1/user/sessions/${sessionId}`, {
        method: 'DELETE',
        headers,
      });
      const data = await res.json();
      if (data.success) {
        if (activeSessionId === sessionId) {
          reset();
        }
        setSessionMessages((prev) => {
          const next = { ...prev };
          delete next[sessionId];
          return next;
        });
        if (expandedSessionId === sessionId) {
          setExpandedSessionId(null);
        }
        await fetchSessions();
      } else {
        alert('Failed to delete session.');
      }
    } catch (err) {
      console.error('Error deleting session:', err);
      alert('Error deleting session.');
    }
  };

  const toggleSessionExpanded = async (sessionId: string) => {
    const nextId = expandedSessionId === sessionId ? null : sessionId;
    setExpandedSessionId(nextId);
    if (nextId) {
      await fetchSessionHistoryPreview(nextId);
    }
  };

  return (
    <header className="relative z-40 shrink-0 border-b border-[#b6924f]/12 bg-[radial-gradient(circle_at_top_left,_rgba(191,149,63,0.14),_transparent_28%),linear-gradient(180deg,_rgba(14,20,31,0.98),_rgba(9,13,21,0.96))] px-5 py-4 backdrop-blur-2xl">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-[#d6b46b] via-[#a87a2d] to-[#0f766e] text-sm font-bold text-[#0b1220] shadow-[0_0_40px_rgba(181,140,63,0.18)]">
            EI
          </div>
          <div>
            <h1 className="font-display text-3xl text-[#f6f1e8]">Equity Intelligence</h1>
            <p className="text-xs text-[#b8ab94]">Premium stock analysis console with live agent observability</p>
          </div>
          {uploaded && (
            <div className="hidden rounded-full border border-[#d4a84c]/25 bg-[#d4a84c]/10 px-3 py-1.5 text-xs text-[#f4d28a] md:block">
              Active statement: {maskStatementLabel(clientName || 'Portfolio')}{clientCode ? ` - ${maskIdentifier(clientCode)}` : ''}
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 lg:justify-end">
          {!uploaded && (
            <button
              onClick={() => setIsDrawerOpen(true)}
              className="rounded-md border border-[#c49a4a]/25 bg-[#c49a4a]/10 px-4 py-2 text-xs font-semibold text-[#f2d18a] transition hover:border-[#d8b15f]/45 hover:bg-[#c49a4a]/16"
            >
              Uploaded statements
            </button>
          )}
          <div className="flex items-center gap-3 rounded-full border border-[#d6b46b]/12 bg-white/[0.04] px-3 py-1.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-[#201a11] to-[#0f172a] text-sm font-bold text-[#f6e3b4]">
              {user?.username?.substring(0, 2).toUpperCase() || 'U'}
            </div>
            <div className="hidden text-left sm:block">
              <p className="text-xs font-semibold text-white">{maskIdentifier(user?.username || 'User')}</p>
              <p className="text-[11px] text-[#a49a89]">{maskEmail(user?.email || 'Workspace account')}</p>
            </div>
            <button onClick={logout} className="text-xs font-semibold text-rose-300 transition hover:text-rose-200">
              Logout
            </button>
          </div>
        </div>
      </div>

      {isDrawerOpen && createPortal(
        <div className="fixed inset-0 z-50 overflow-hidden">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setIsDrawerOpen(false)} />
          <div className="absolute inset-y-0 right-0 flex max-w-full pl-10">
            <div className="flex h-full w-screen max-w-xl flex-col border-l border-[#d4a84c]/12 bg-[linear-gradient(180deg,_#0d131d,_#091019)] p-6 shadow-2xl">
              <div className="mb-6 flex items-start justify-between border-b border-white/10 pb-4">
                <div>
                  <h2 className="text-xl font-semibold text-[#f6f1e8]">Uploaded statements</h2>
                  <p className="mt-1 text-xs text-[#b8ab94]">Open a statement, inspect its query history, or jump into its developer trace.</p>
                </div>
                <button onClick={() => setIsDrawerOpen(false)} className="text-xl text-[#8fa1af] transition hover:text-white">
                  ×
                </button>
              </div>

              <div className="mb-4 rounded-2xl border border-[#d4a84c]/12 bg-[#d4a84c]/6 px-4 py-3 text-xs text-[#dbc189]">
                {sessions.length} statement session{sessions.length === 1 ? '' : 's'} available
              </div>

              <div className="flex-1 space-y-4 overflow-y-auto pr-1">
                {loading ? (
                  <div className="flex items-center justify-center py-12">
                    <div className="h-6 w-6 animate-spin rounded-full border-2 border-[#d4a84c] border-t-transparent" />
                  </div>
                ) : sessions.length === 0 ? (
                  <div className="rounded-[24px] border border-white/10 bg-white/[0.03] px-5 py-8 text-center text-sm text-[#8fa1af]">
                    No brokerage statements uploaded yet.
                  </div>
                ) : (
                  sessions.map((session) => {
                    const isActive = activeSessionId === session._id;
                    const isExpanded = expandedSessionId === session._id;
                    const history = sessionMessages[session._id] || [];
                    const userQuestions = history.filter((msg) => msg.role === 'user');

                    return (
                      <div
                        key={session._id}
                        className={`rounded-[26px] border p-4 transition ${
                          isActive
                            ? 'border-[#d4a84c]/35 bg-[#d4a84c]/10 shadow-[0_0_30px_rgba(181,140,63,0.08)]'
                            : 'border-white/8 bg-white/[0.03] hover:border-white/14'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-white" title={session.original_filename}>
                              {maskStatementLabel(session.original_filename || 'Untitled statement')}
                            </p>
                            <p className="mt-1 text-[11px] text-[#a49a89]">{session.created_at ? new Date(session.created_at).toLocaleString() : 'Unknown upload time'}</p>
                          </div>
                          {isActive && (
                            <span className="rounded-full bg-[#d4a84c]/15 px-2 py-1 text-[10px] font-semibold text-[#f2d18a]">
                              Active
                            </span>
                          )}
                        </div>

                        <div className="mt-4 grid grid-cols-4 gap-2">
                          <button
                            onClick={() => handleActivateSession(session._id)}
                            className="rounded-xl bg-gradient-to-r from-[#d4a84c] to-[#0f766e] px-3 py-2 text-[11px] font-semibold text-[#081018]"
                          >
                            Open
                          </button>
                          <button
                            onClick={() => toggleSessionExpanded(session._id)}
                            className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-[11px] font-semibold text-white"
                          >
                            History
                          </button>
                          <button
                            onClick={() => {
                              setIsDrawerOpen(false);
                              navigate(`/developer?session_id=${session._id}`);
                            }}
                            className="rounded-xl border border-[#0ea5a4]/30 bg-[#0ea5a4]/10 px-3 py-2 text-[11px] font-semibold text-[#8ff2ee]"
                          >
                            Trace
                          </button>
                          <button
                            onClick={() => handleDeleteSession(session._id)}
                            className="rounded-xl border border-rose-400/30 bg-rose-400/10 px-3 py-2 text-[11px] font-semibold text-rose-300"
                          >
                            Delete
                          </button>
                        </div>

                        {isExpanded && (
                          <div className="mt-4 rounded-2xl border border-white/8 bg-[#0a1119] p-4">
                            <div className="mb-3 flex items-center justify-between">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#b8ab94]">Query history</p>
                              <span className="text-[11px] text-[#8fa1af]">{userQuestions.length} user quer{userQuestions.length === 1 ? 'y' : 'ies'}</span>
                            </div>

                            {historyLoadingId === session._id ? (
                              <div className="flex items-center gap-2 py-4 text-sm text-[#b8ab94]">
                                <div className="h-4 w-4 animate-spin rounded-full border-2 border-[#d4a84c] border-t-transparent" />
                                Loading statement history...
                              </div>
                            ) : userQuestions.length === 0 ? (
                              <div className="rounded-xl border border-white/8 bg-white/[0.03] px-4 py-4 text-sm text-[#8fa1af]">
                                No chat history yet for this statement. Uploading created the session, but no analysis query has been run on it yet.
                              </div>
                            ) : (
                              <div className="space-y-2">
                                {userQuestions.map((msg) => {
                                  const pairedAgentReply = history.find((candidate) => candidate.role === 'agent' && candidate.timestamp >= msg.timestamp);
                                  return (
                                    <div key={msg.id} className="rounded-xl border border-white/8 bg-white/[0.03] px-4 py-3">
                                      <p className="text-sm font-medium text-white">{maskFreeText(msg.content)}</p>
                                      
                                      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-[#8fa1af]">
                                        <span>{new Date(msg.timestamp).toLocaleString()}</span>
                                        {pairedAgentReply?.agentUsed && (
                                          <span className="rounded-full border border-[#d4a84c]/20 bg-[#d4a84c]/10 px-2 py-0.5 text-[#f2d18a]">
                                            {pairedAgentReply.agentUsed.replace('_agent', '')}
                                          </span>
                                        )}
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </header>
  );
}
