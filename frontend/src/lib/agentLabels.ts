export const agentLabels: Record<string, string> = {
  portfolio_agent: 'Portfolio Agent',
  pnl_agent: 'P&L Agent',
  dividend_agent: 'Dividend Agent',
  supervisor: 'Supervisor',
  auto: 'Auto (Supervisor Routes)',
  excel_reader_tool: 'Excel Reader',
};

export const agentIcons: Record<string, string> = {
  portfolio_agent: '📊',
  pnl_agent: '💰',
  dividend_agent: '📈',
  supervisor: '🤖',
  auto: '🧠',
};

export function getAgentLabel(id: string): string {
  return agentLabels[id] || id;
}

export function getAgentIcon(id: string): string {
  return agentIcons[id] || '🤖';
}
