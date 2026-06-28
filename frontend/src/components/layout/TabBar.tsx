import { useAppStore, type Tab } from '../../store/appStore';

const tabs: Array<{ id: Tab; label: string; description: string }> = [
  { id: 'chat', label: 'Chat', description: 'Ask the agents' },
  { id: 'dashboard', label: 'Dashboard', description: 'Metrics and visuals' },
  { id: 'raw', label: 'Raw Data', description: 'Uploaded rows and mappings' },
];

export default function TabBar() {
  const { activeTab, setActiveTab } = useAppStore();

  return (
    <div className="shrink-0 border-b border-white/10 bg-[#101a28]/85 px-4 py-3 backdrop-blur xl:hidden">
      <div className="flex flex-wrap gap-3">
        {tabs.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`min-w-[170px] rounded-2xl border px-4 py-3 text-left transition ${
                active
                  ? 'border-sky-400/40 bg-sky-400/10 shadow-[0_0_0_1px_rgba(56,189,248,0.12)]'
                  : 'border-white/8 bg-white/[0.03] hover:border-white/15 hover:bg-white/[0.05]'
              }`}
            >
              <p className={`text-sm font-semibold ${active ? 'text-white' : 'text-[#d7e2e8]'}`}>{tab.label}</p>
              <p className="mt-1 text-xs text-[#8fa1af]">{tab.description}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
