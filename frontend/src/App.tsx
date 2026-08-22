import { useState } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import SagePopup from './components/SagePopup';
import Sidebar from './components/Sidebar';
import { useCapabilities } from './hooks/useCapabilities';
import { useTheme } from './hooks/useTheme';
import { useVoice } from './hooks/useVoice';
import ArticlePage from './pages/ArticlePage';
import ChatPage from './pages/ChatPage';
import SearchPage from './pages/SearchPage';

/** The site root used to be the chat; it now opens the news.
 *
 *  Chat links minted before the move carry `/?conversation=<id>` and may be
 *  bookmarked, so the conversation is forwarded to its new home rather than
 *  dropped on the floor. `replace` keeps the redirect out of the history —
 *  without it the back button bounces between `/` and `/search`.
 */
export function RootRedirect() {
  const { search } = useLocation();
  const conversation = new URLSearchParams(search).get('conversation');
  return <Navigate to={conversation ? `/chat${search}` : '/search'} replace />;
}

export default function App() {
  const [sidebarRefresh, setSidebarRefresh] = useState(0);
  const { theme, setTheme } = useTheme();
  // Probed once here rather than inside each feature that gates on it —
  // playback and voice input would otherwise issue the same request twice.
  const capabilities = useCapabilities();
  // Voice lives here, beside theme, so the sidebar's two copies and the chat
  // page all read one source rather than three drifting ones.
  const voice = useVoice(capabilities.tts);
  return (
    // below md the Sidebar contributes a top bar instead of a rail, so the
    // shell stacks; from md it is the familiar rail-beside-content row
    <div className="flex h-full flex-col md:flex-row">
      <Sidebar
        refreshKey={sidebarRefresh}
        theme={theme}
        onSelectTheme={setTheme}
        voice={voice.voice}
        onSelectVoice={voice.setVoice}
        voiceAvailable={voice.available}
      />
      <main className="min-h-0 min-w-0 flex-1">
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/search" element={<SearchPage />} />
          <Route
            path="/chat"
            element={
              <ChatPage
                onConversationChange={() => setSidebarRefresh((n) => n + 1)}
                voice={voice}
                voiceInput={capabilities.stt}
              />
            }
          />
          {/* Guardian article IDs contain slashes → splat route */}
          <Route path="/article/*" element={<ArticlePage />} />
        </Routes>
      </main>
      {/* outside <main> so neither the button nor its panel is clipped by a
          page's own scroll container */}
      <SagePopup
        voiceInput={capabilities.stt}
        voiceAvailable={voice.available}
        autoRead={voice.voice === 'on'}
        onConversationChange={() => setSidebarRefresh((n) => n + 1)}
      />
    </div>
  );
}
