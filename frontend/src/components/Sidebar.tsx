import { useCallback, useEffect, useState } from 'react';
import { Link, NavLink, useNavigate, useSearchParams } from 'react-router-dom';
import { SECTIONS, SECTION_GROUPS } from '../constants/sections';
import ThemeToggle from './ThemeToggle';
import type { Theme } from '../hooks/useTheme';
import { deleteAllConversations, deleteConversation, listConversations, listSources } from '../services/api';
import type { ConversationSummary, NewsSourceInfo } from '../types';

export default function Sidebar({
  refreshKey,
  theme,
  onSelectTheme,
}: {
  refreshKey?: number;
  theme: Theme;
  onSelectTheme: (theme: Theme) => void;
}) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [sources, setSources] = useState<NewsSourceInfo[]>([]);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const openConversationId = searchParams.get('conversation');

  const load = useCallback(() => {
    listConversations()
      .then(setConversations)
      .catch(() => setConversations([]));
  }, []);

  useEffect(load, [load, refreshKey]);
  useEffect(() => {
    listSources()
      .then(setSources)
      .catch(() => setSources([]));
  }, []);

  const removeOne = async (id: string) => {
    setPendingDelete(id);
    const previous = conversations;
    setConversations((prev) => prev.filter((c) => c.id !== id));
    try {
      await deleteConversation(id);
      if (openConversationId === id) navigate('/', { state: { newChat: Date.now() } });
    } catch {
      setConversations(previous);
    } finally {
      setPendingDelete(null);
    }
  };

  const removeAll = async () => {
    if (!window.confirm(`Delete all ${conversations.length} chats? This cannot be undone.`)) return;
    const previous = conversations;
    setConversations([]);
    try {
      await deleteAllConversations();
      navigate('/', { state: { newChat: Date.now() } });
    } catch {
      setConversations(previous);
    }
  };

  const navClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
      isActive ? 'bg-white/10 text-white' : 'text-accent-200/80 hover:bg-white/5 hover:text-white'
    }`;

  return (
    <aside className="hidden w-[264px] shrink-0 flex-col bg-sidebar-gradient text-white md:flex">
      {/* the logo returns to the landing screen; without fresh state the
          route is already "/" and the open conversation would stay mounted */}
      <Link
        to="/"
        state={{ newChat: Date.now() }}
        className="flex items-center gap-2.5 border-b border-white/10 px-5 py-4 transition-colors hover:bg-white/5"
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-gradient text-[15px] font-bold shadow-glow">
          N
        </span>
        <span>
          <span className="block text-[15px] font-semibold leading-tight">News AI</span>
          <span className="block text-[11px] text-accent-200/50">Research assistant</span>
        </span>
      </Link>

      <div className="space-y-1 p-3">
        <button
          onClick={() => navigate('/', { state: { newChat: Date.now() } })}
          className="flex w-full items-center gap-2 rounded-lg bg-brand-gradient px-3 py-2 text-sm font-semibold shadow-glow transition-opacity hover:opacity-90"
        >
          <span className="text-base leading-none">+</span> New chat
        </button>
        <NavLink to="/search" className={navClass}>
          Search news
        </NavLink>
      </div>

      <div className="mt-1 flex-1 overflow-y-auto px-3">
        {SECTION_GROUPS.map((group) => (
          <div key={group} className="pb-2">
            <div className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-white/35">
              {group}
            </div>
            <div className="grid grid-cols-2 gap-x-1 gap-y-0.5">
              {SECTIONS.filter((s) => s.group === group).map((section) => (
                <Link
                  key={section.id}
                  to={`/search?section=${section.id}`}
                  className="truncate rounded-lg px-2.5 py-1.5 text-[12.5px] text-white/70 transition-colors hover:bg-white/5 hover:text-white"
                >
                  {section.label}
                </Link>
              ))}
            </div>
          </div>
        ))}

        <div className="flex items-center justify-between px-3 pb-1.5">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-white/35">
            Recent chats
          </span>
          {conversations.length > 0 && (
            <button
              onClick={removeAll}
              className="text-[10px] font-medium text-white/35 transition-colors hover:text-red-300"
              title="Delete all chats"
            >
              Clear all
            </button>
          )}
        </div>
        <div className="space-y-0.5 pb-4">
          {conversations.length === 0 && (
            <div className="px-3 py-2 text-xs text-white/30">No conversations yet</div>
          )}
          {conversations.map((conversation) => (
            <div
              key={conversation.id}
              className={`group flex items-center rounded-lg transition-colors ${
                openConversationId === conversation.id ? 'bg-white/10' : 'hover:bg-white/5'
              }`}
            >
              <Link
                to={`/?conversation=${conversation.id}`}
                className="min-w-0 flex-1 truncate px-3 py-2 text-[13px] text-white/80"
                title={conversation.title}
              >
                {conversation.title}
              </Link>
              <button
                onClick={() => removeOne(conversation.id)}
                disabled={pendingDelete === conversation.id}
                aria-label={`Delete chat: ${conversation.title}`}
                title="Delete chat"
                className="mr-1.5 rounded p-1 text-white/25 opacity-0 transition-all hover:bg-red-500/20 hover:text-red-300 focus:opacity-100 group-hover:opacity-100 disabled:opacity-20"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 6h18M8 6V4a1 1 0 011-1h6a1 1 0 011 1v2M19 6l-1 14a1 1 0 01-1 1H7a1 1 0 01-1-1L5 6M10 11v6M14 11v6" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-white/10 p-2">
        <ThemeToggle theme={theme} onSelect={onSelectTheme} />
      </div>

      <div className="border-t border-white/10 px-5 py-3 text-[10px] leading-relaxed text-white/35">
        {sources.length > 0 ? (
          <>Sourced from {sources.map((s) => s.name).join(' · ')}</>
        ) : (
          <>Sourced from leading newsrooms</>
        )}
      </div>
    </aside>
  );
}
