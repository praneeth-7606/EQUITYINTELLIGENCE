import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Topbar from '../components/layout/Topbar';

export default function ProjectsPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // New Project Form state
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState('Active');
  const [cost, setCost] = useState('0');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const fetchProjects = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('access_token');
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      const res = await fetch('/api/v1/projects', { headers });
      const data = await res.json();
      if (data.success) {
        setProjects(data.projects);
      } else {
        setError(data.detail || 'Failed to load projects');
      }
    } catch (err) {
      setError('Network error loading projects');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    try {
      const token = localStorage.getItem('access_token');
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch('/api/v1/projects', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          project_name: name,
          project_status: status,
          project_start_date: startDate || undefined,
          project_end_date: endDate || undefined,
          project_cost: parseFloat(cost) || 0.0,
          project_description: description
        })
      });
      const data = await res.json();
      if (data.success) {
        setShowForm(false);
        setName('');
        setDescription('');
        setStatus('Active');
        setCost('0');
        setStartDate('');
        setEndDate('');
        fetchProjects();
      } else {
        alert(data.detail || 'Failed to create project');
      }
    } catch (err) {
      alert('Network error creating project');
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-canvas text-text font-sans">
      <Topbar />
      <main className="flex-1 p-6 max-w-4xl mx-auto w-full space-y-6">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold text-white">My Projects</h1>
            <p className="text-xs text-muted">Group your brokerage uploads into logical work divisions</p>
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 bg-gold hover:bg-goldlt text-canvas text-xs font-bold rounded-lg transition-colors"
          >
            {showForm ? 'Cancel' : '+ New Project'}
          </button>
        </div>

        {error && (
          <div className="p-3 bg-loss/10 border border-loss/20 rounded-lg text-xs text-loss">
            {error}
          </div>
        )}

        {showForm && (
          <form onSubmit={handleCreateProject} className="bg-surface border border-border p-5 rounded-xl space-y-4">
            <h3 className="text-sm font-bold text-white">Create New Project</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
              <div className="space-y-1">
                <label className="text-muted font-semibold block">Project Name *</label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full p-2 bg-canvas border border-border rounded text-white"
                  placeholder="e.g. Q1 Portfolio Review"
                />
              </div>

              <div className="space-y-1">
                <label className="text-muted font-semibold block">Status</label>
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                  className="w-full p-2 bg-canvas border border-border rounded text-white"
                >
                  <option value="Active">Active</option>
                  <option value="Completed">Completed</option>
                  <option value="Planning">Planning</option>
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-muted font-semibold block">Start Date</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full p-2 bg-canvas border border-border rounded text-white"
                />
              </div>

              <div className="space-y-1">
                <label className="text-muted font-semibold block">End Date</label>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="w-full p-2 bg-canvas border border-border rounded text-white"
                />
              </div>

              <div className="space-y-1">
                <label className="text-muted font-semibold block">Estimated Cost ($)</label>
                <input
                  type="number"
                  min="0"
                  value={cost}
                  onChange={(e) => setCost(e.target.value)}
                  className="w-full p-2 bg-canvas border border-border rounded text-white"
                />
              </div>

              <div className="space-y-1 sm:col-span-2">
                <label className="text-muted font-semibold block">Description</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                  className="w-full p-2 bg-canvas border border-border rounded text-white"
                  placeholder="Describe this project group's goal..."
                />
              </div>
            </div>
            <button
              type="submit"
              className="w-full py-2 bg-gold text-canvas font-bold text-xs rounded-lg hover:bg-goldlt transition-colors"
            >
              Create Project
            </button>
          </form>
        )}

        {loading ? (
          <div className="flex justify-center py-12">
            <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
          </div>
        ) : projects.length === 0 ? (
          <div className="p-8 text-center bg-surface border border-border rounded-xl text-muted text-xs">
            No projects found. Create a project to start organizing your files.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {projects.map((proj) => (
              <div
                key={proj._id}
                onClick={() => navigate(`/project/${proj._id}`)}
                className="p-5 bg-surface border border-border rounded-xl cursor-pointer hover:border-gold/50 transition-all space-y-4"
              >
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="text-sm font-bold text-white">{proj.project_name}</h3>
                    <p className="text-[10px] text-muted line-clamp-1">{proj.project_description}</p>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-[#1baf7a]/15 text-[#1baf7a] border border-[#1baf7a]/20">
                    {proj.project_status}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2 text-[10px] text-[#888780] font-mono border-t border-border/40 pt-3">
                  <div>
                    <span className="block text-muted text-[8px] uppercase">Start</span>
                    <span className="text-white">{proj.project_start_date}</span>
                  </div>
                  <div>
                    <span className="block text-muted text-[8px] uppercase">End</span>
                    <span className="text-white">{proj.project_end_date}</span>
                  </div>
                  <div>
                    <span className="block text-muted text-[8px] uppercase">Cost</span>
                    <span className="text-[#1baf7a] font-bold">${proj.project_cost}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
