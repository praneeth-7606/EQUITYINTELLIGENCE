import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Topbar from '../components/layout/Topbar';
import { useAppStore } from '../store/appStore';

export default function ProjectDetailPage() {
  const { project_id } = useParams<{ project_id: string }>();
  const navigate = useNavigate();
  const { loadSessionHistory } = useAppStore();

  const [project, setProject] = useState<any>(null);
  const [files, setFiles] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchProjectDetails = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('access_token');
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      const res = await fetch(`/api/v1/projects/${project_id}`, { headers });
      const data = await res.json();
      if (data.success) {
        setProject(data.project);
        setFiles(data.files);
      } else {
        setError(data.detail || 'Failed to load project details');
      }
    } catch (err) {
      setError('Network error loading project details');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (project_id) {
      fetchProjectDetails();
    }
  }, [project_id]);

  const handleOpenChat = async (sessionId: string) => {
    await loadSessionHistory(sessionId);
    navigate('/');
  };

  if (loading) {
    return (
      <div className="flex flex-col min-h-screen bg-canvas text-text font-sans">
        <Topbar />
        <div className="flex-1 flex items-center justify-center">
          <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="flex flex-col min-h-screen bg-canvas text-text font-sans">
        <Topbar />
        <main className="flex-1 p-6 max-w-4xl mx-auto w-full">
          <div className="p-4 bg-loss/10 border border-loss/20 rounded-xl text-center text-loss">
            {error || 'Project not found.'}
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen bg-canvas text-text font-sans">
      <Topbar />
      <main className="flex-1 p-6 max-w-4xl mx-auto w-full space-y-6">
        <div className="flex justify-between items-center">
          <h2 className="text-2xl font-bold text-white">Project Workspace</h2>
          <button
            onClick={() => navigate('/projects')}
            className="text-xs font-semibold text-gold hover:text-goldlt hover:underline"
          >
            &larr; Back to Projects
          </button>
        </div>

        {/* Project Metadata Card */}
        <div className="bg-surface border border-border p-6 rounded-2xl shadow-xl space-y-4">
          <h3 className="text-sm font-bold text-white border-b border-border pb-2">Project Metadata</h3>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div>
              <span className="text-muted block font-semibold mb-1 uppercase tracking-wider text-[9px]">Project Name</span>
              <span className="text-white font-medium text-sm" id="project_name">{project.project_name}</span>
            </div>

            <div>
              <span className="text-muted block font-semibold mb-1 uppercase tracking-wider text-[9px]">Status</span>
              <span className="text-white font-medium text-sm" id="project_status">{project.project_status}</span>
            </div>

            <div>
              <span className="text-muted block font-semibold mb-1 uppercase tracking-wider text-[9px]">Start Date</span>
              <span className="text-white font-medium font-mono text-sm" id="project_start_date">{project.project_start_date}</span>
            </div>

            <div>
              <span className="text-muted block font-semibold mb-1 uppercase tracking-wider text-[9px]">End Date</span>
              <span className="text-white font-medium font-mono text-sm" id="project_end_date">{project.project_end_date}</span>
            </div>

            <div>
              <span className="text-muted block font-semibold mb-1 uppercase tracking-wider text-[9px]">Cost</span>
              <span className="text-[#1baf7a] font-bold font-mono text-sm" id="project_cost">${project.project_cost}</span>
            </div>

            <div>
              <span className="text-muted block font-semibold mb-1 uppercase tracking-wider text-[9px]">Created At</span>
              <span className="text-white font-medium font-mono text-sm" id="project_created_at">{project.created_at}</span>
            </div>

            <div>
              <span className="text-muted block font-semibold mb-1 uppercase tracking-wider text-[9px]">Updated At</span>
              <span className="text-white font-medium font-mono text-sm" id="project_updated_at">{project.updated_at}</span>
            </div>

            <div className="md:col-span-2">
              <span className="text-muted block font-semibold mb-1 uppercase tracking-wider text-[9px]">Description</span>
              <span className="text-white text-xs leading-relaxed" id="project_description">{project.project_description}</span>
            </div>
          </div>
        </div>

        {/* Files Table */}
        <div className="space-y-4">
          <h3 className="text-lg font-bold text-white">Files in Project</h3>
          <div className="bg-surface border border-border rounded-2xl shadow-xl overflow-hidden p-6">
            <div className="overflow-x-auto">
              <table className="min-w-full table-auto text-left text-xs">
                <thead>
                  <tr className="border-b border-border/80 bg-canvas/30 text-muted uppercase font-bold tracking-wider">
                    <th className="px-4 py-2.5">File ID</th>
                    <th className="px-4 py-2.5">Original Filename</th>
                    <th className="px-4 py-2.5">Uploaded Date</th>
                    <th className="px-4 py-2.5 text-center">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {files.map((file) => (
                    <tr key={file.file_id} className="border-b border-border/40 hover:bg-canvas/20 transition-colors">
                      <td className="px-4 py-3 text-white font-mono">{file.file_id}</td>
                      <td className="px-4 py-3 text-white font-medium">{file.original_filename}</td>
                      <td className="px-4 py-3 text-muted">{new Date(file.uploaded_at).toLocaleString()}</td>
                      <td className="px-4 py-3 text-center space-x-3">
                        <button
                          disabled={!file.session_id}
                          onClick={() => handleOpenChat(file.session_id)}
                          className="px-2.5 py-1 text-[10px] font-bold bg-gold text-canvas rounded hover:bg-goldlt transition-colors disabled:opacity-50"
                        >
                          Open Chat
                        </button>
                        <button
                          disabled={!file.session_id}
                          onClick={() => navigate(`/developer?session_id=${file.session_id}`)}
                          className="px-2.5 py-1 text-[10px] font-bold border border-[#1baf7a]/30 text-[#1baf7a] rounded hover:border-[#1baf7a] hover:bg-[#1baf7a]/5 transition-colors disabled:opacity-50"
                        >
                          Dev Portal
                        </button>
                      </td>
                    </tr>
                  ))}
                  {files.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-4 py-8 text-center text-muted">
                        No statements uploaded to this project yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
