import { useCallback, useEffect, useState } from 'react';
import { Link, NavLink, useNavigate, useSearchParams } from 'react-router-dom';
import { SECTIONS } from '../constants/sections';
import { deleteAllConversations, deleteConversation, listConversations } from '../services/api';
import type { ConversationSummary } from '../types';

export default function Sidebar({ refreshKey }: { refreshKey?: number }) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
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

  const removeOne = async (id: string) => {
    setPendingDelete(id);
    // optimistic: drop it immediately, restore on failure
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

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `block rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
      isActive ? 'bg-brand-800 text-white' : 'text-brand-100 hover:bg-brand-800/60'
    }`;

  return (
    <aside className="hidden md:flex w-64 shrink-0 flex-col bg-brand-900 text-white">
      <Link to="/" className="px-4 py-5 border-b border-brand-800">
        <div className="font-serif text-xl font-bold leading-tight">News AI</div>
        <div className="text-xs text-brand-100/80 mt-0.5">Research Assistant</div>
      </Link>

      <div className="p-3 space-y-1">
        <button
          onClick={() => navigate('/', { state: { newChat: Date.now() } })}
          className="w-full rounded-lg bg-brand-500 hover:bg-brand-600 px-3 py-2 text-sm font-semibold text-left transition-colors"
        >
          + New Chat
        </button>
        <NavLink to="/search" className={linkClass}>
          Search News
        </NavLink>
      </div>

      <div className="px-3 pt-2">
        <div className="px-3 pb-1 text-[11px] uppercase tracking-wider text-brand-100/60">Sections</div>
        <div className="space-y-0.5">
          {SECTIONS.map((section) => (
            <Link
              key={section.id}
              to={`/search?section=${section.id}`}
              className="block rounded-lg px-3 py-1.5 text-sm text-brand-100 hover:bg-brand-800/60"
            >
              {section.label}
            </Link>
          ))}
        </div>
      </div>

      <div className="px-3 pt-4 flex-1 overflow-y-auto">
        <div className="flex items-center justify-between px-3 pb-1">
          <span className="text-[11px] uppercase tracking-wider text-brand-100/60">Recent Chats</span>
          {conversations.length > 0 && (
            <button
              onClick={removeAll}
              className="text-[11px] text-brand-100/50 hover:text-red-300 transition-colors"
              title="Delete all chats"
            >
              Clear all
            </button>
          )}
        </div>
        <div className="space-y-0.5 pb-4">
          {conversations.length === 0 && (
            <div className="px-3 py-2 text-xs text-brand-100/50">No conversations yet</div>
          )}
          {conversations.map((conversation) => (
            <div
              key={conversation.id}
              className="group flex items-center rounded-lg hover:bg-brand-800/60"
            >
              <Link
                to={`/?conversation=${conversation.id}`}
                className="min-w-0 flex-1 truncate px-3 py-1.5 text-sm text-brand-100"
                title={conversation.title}
              >
                {conversation.title}
              </Link>
              <button
                onClick={() => removeOne(conversation.id)}
                disabled={pendingDelete === conversation.id}
                aria-label={`Delete chat: ${conversation.title}`}
                title="Delete chat"
                className="mr-1 rounded p-1 text-brand-100/40 opacity-0 transition-opacity hover:bg-red-500/20 hover:text-red-300 focus:opacity-100 group-hover:opacity-100 disabled:opacity-30"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 6h18M8 6V4a1 1 0 011-1h6a1 1 0 011 1v2M19 6l-1 14a1 1 0 01-1 1H7a1 1 0 01-1-1L5 6M10 11v6M14 11v6" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="p-4 text-[11px] text-brand-100/50 border-t border-brand-800">
        Powered by the Guardian Open Platform
      </div>
    </aside>
  );
}
