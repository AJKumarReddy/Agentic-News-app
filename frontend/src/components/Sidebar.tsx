import { useCallback, useEffect, useState } from 'react';
import { Link, NavLink, useNavigate, useSearchParams } from 'react-router-dom';
import { SECTIONS } from '../constants/sections';
import { deleteAllConversations, deleteConversation, listConversations, listSources } from '../services/api';
import type { ConversationSummary, NewsSourceInfo } from '../types';

export default function Sidebar({ refreshKey }: { refreshKey?: number }) {
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
      isActive ? 'bg-white/10 text-white' : 'text-brand-100/80 hover:bg-white/5 hover:text-white'
    }`;

  return (
    <aside className="hidden w-[264px] shrink-0 flex-col bg-brand-950 text-white md:flex">
      <Link to="/" className="flex items-center gap-2.5 border-b border-white/10 px-5 py-4">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500 text-[15px] font-bold">
          N
        </span>
        <span>
          <span className="block text-[15px] font-semibold leading-tight">News AI</span>
          <span className="block text-[11px] text-brand-100/60">Research assistant</span>
        </span>
      </Link>

      <div className="space-y-1 p-3">
        <button
          onClick={() => navigate('/', { state: { newChat: Date.now() } })}
          className="flex w-full items-center gap-2 rounded-lg bg-brand-500 px-3 py-2 text-sm font-semibold transition-colors hover:bg-brand-400"
        >
          <span className="text-base leading-none">+</span> New chat
        </button>
        <NavLink to="/search" className={navClass}>
          Search news
        </NavLink>
      </div>

      <div className="px-3 pt-2">
        <div className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-brand-100/40">
          Sections
        </div>
        <div className="space-y-0.5">
          {SECTIONS.map((section) => (
            <Link
              key={section.id}
              to={`/search?section=${section.id}`}
              className="block rounded-lg px-3 py-1.5 text-[13px] text-brand-100/75 transition-colors hover:bg-white/5 hover:text-white"
            >
              {section.label}
            </Link>
          ))}
        </div>
      </div>

      <div className="mt-4 flex-1 overflow-y-auto px-3">
        <div className="flex items-center justify-between px-3 pb-1.5">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-brand-100/40">
            Recent chats
          </span>
          {conversations.length > 0 && (
            <button
              onClick={removeAll}
              className="text-[10px] font-medium text-brand-100/40 transition-colors hover:text-red-300"
              title="Delete all chats"
            >
              Clear all
            </button>
          )}
        </div>
        <div className="space-y-0.5 pb-4">
          {conversations.length === 0 && (
            <div className="px-3 py-2 text-xs text-brand-100/35">No conversations yet</div>
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
                className="min-w-0 flex-1 truncate px-3 py-2 text-[13px] text-brand-100/85"
                title={conversation.title}
              >
                {conversation.title}
              </Link>
              <button
                onClick={() => removeOne(conversation.id)}
                disabled={pendingDelete === conversation.id}
                aria-label={`Delete chat: ${conversation.title}`}
                title="Delete chat"
                className="mr-1.5 rounded p-1 text-brand-100/30 opacity-0 transition-all hover:bg-red-500/20 hover:text-red-300 focus:opacity-100 group-hover:opacity-100 disabled:opacity-20"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 6h18M8 6V4a1 1 0 011-1h6a1 1 0 011 1v2M19 6l-1 14a1 1 0 01-1 1H7a1 1 0 01-1-1L5 6M10 11v6M14 11v6" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-white/10 px-5 py-3.5 text-[10px] leading-relaxed text-brand-100/40">
        {sources.length > 0 ? (
          <>Sourced from {sources.map((s) => s.name).join(' · ')}</>
        ) : (
          <>Sourced from leading newsrooms</>
        )}
      </div>
    </aside>
  );
}
