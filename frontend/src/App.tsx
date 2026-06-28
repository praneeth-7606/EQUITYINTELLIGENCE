import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { useAppStore } from './store/appStore';
import SheetDropZone from './components/upload/SheetDropZone';
import Topbar from './components/layout/Topbar';
import Sidebar from './components/layout/Sidebar';
import TabBar from './components/layout/TabBar';
import ChatThread from './components/chat/ChatThread';
import ChatInput from './components/chat/ChatInput';
import DashboardView from './components/dashboard/DashboardView';
import RawDataView from './components/rawdata/RawDataView';

// Auth Pages & Context
import { AuthProvider } from './auth/AuthContext';
import { ProtectedRoute } from './auth/ProtectedRoute';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import DeveloperDashboard from './pages/developer/DeveloperDashboard';

function MainContent() {
  const { activeTab } = useAppStore();

  switch (activeTab) {
    case 'chat':
      return (
        <div className="flex flex-col flex-1 min-h-0">
          <ChatThread />
          <ChatInput />
        </div>
      );
    case 'dashboard':
      return <DashboardView />;
    case 'raw':
      return <RawDataView />;
    default:
      return null;
  }
}

function PlatformMain() {
  const { uploaded } = useAppStore();

  if (!uploaded) {
    return (
      <div className="h-screen flex flex-col bg-canvas overflow-hidden">
        <Topbar />
        <div className="flex-1 overflow-y-auto bg-canvas px-6 py-8">
          <SheetDropZone />
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-canvas overflow-hidden">
      <Topbar />
      <main className="flex-1 flex min-h-0 min-w-0">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <TabBar />
          <MainContent />
        </div>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Auth Routes */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />

          {/* Protected Developer Dashboard */}
          <Route
            path="/developer"
            element={
              <ProtectedRoute>
                <DeveloperDashboard />
              </ProtectedRoute>
            }
          />

          {/* Main App (Protected) */}
          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <PlatformMain />
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
