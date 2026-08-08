import { useState } from 'react';
import { Route, Routes } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import ArticlePage from './pages/ArticlePage';
import ChatPage from './pages/ChatPage';
import SearchPage from './pages/SearchPage';

export default function App() {
  const [sidebarRefresh, setSidebarRefresh] = useState(0);
  return (
    <div className="flex h-full">
      <Sidebar refreshKey={sidebarRefresh} />
      <main className="min-w-0 flex-1">
        <Routes>
          <Route
            path="/"
            element={<ChatPage onConversationChange={() => setSidebarRefresh((n) => n + 1)} />}
          />
          <Route path="/search" element={<SearchPage />} />
          {/* Guardian article IDs contain slashes → splat route */}
          <Route path="/article/*" element={<ArticlePage />} />
        </Routes>
      </main>
    </div>
  );
}
