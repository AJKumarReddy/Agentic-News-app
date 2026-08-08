import { useEffect, useState } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { listConversations } from '../services/api';
import type { ConversationSummary } from '../types';

const SECTIONS = [
  { id: 'technology', label: 'Technology' },
  { id: 'politics', label: 'Politics' },
  { id: 'business', label: 'Business' },
  { id: 'world', label: 'World' },
  { id: 'environment', label: 'Environment' },
];

export default function Sidebar({ refreshKey }: { refreshKey?: number }) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    listConversations()
      .then(setConversations)
      .catch(() => setConversations([]));
  }, [refreshKey]);

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `block rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
      isActive ? 'bg-guardian-800 text-white' : 'text-guardian-100 hover:bg-guardian-800/60'
    }`;

  return (
    <aside className="hidden md:flex w-64 shrink-0 flex-col bg-guardian-900 text-white">
      <Link to="/" className="px-4 py-5 border-b border-guardian-800">
        <div className="font-serif text-xl font-bold leading-tight">Guardian AI</div>
        <div className="text-xs text-guardian-100/80 mt-0.5">News Research Assistant</div>
      </Link>

      <div className="p-3 space-y-1">
        <button
          onClick={() => navigate('/', { state: { newChat: Date.now() } })}
          className="w-full rounded-lg bg-guardian-500 hover:bg-guardian-600 px-3 py-2 text-sm font-semibold text-left transition-colors"
        >
          + New Chat
        </button>
        <NavLink to="/search" className={linkClass}>
          Search News
        </NavLink>
      </div>

      <div className="px-3 pt-2">
        <div className="px-3 pb-1 text-[11px] uppercase tracking-wider text-guardian-100/60">Sections</div>
        <div className="space-y-0.5">
          {SECTIONS.map((section) => (
            <Link
              key={section.id}
              to={`/search?section=${section.id}`}
              className="block rounded-lg px-3 py-1.5 text-sm text-guardian-100 hover:bg-guardian-800/60"
            >
              {section.label}
            </Link>
          ))}
        </div>
      </div>

      <div className="px-3 pt-4 flex-1 overflow-y-auto">
        <div className="px-3 pb-1 text-[11px] uppercase tracking-wider text-guardian-100/60">Recent Chats</div>
        <div className="space-y-0.5 pb-4">
          {conversations.length === 0 && (
            <div className="px-3 py-2 text-xs text-guardian-100/50">No conversations yet</div>
          )}
          {conversations.map((conversation) => (
            <Link
              key={conversation.id}
              to={`/?conversation=${conversation.id}`}
              className="block truncate rounded-lg px-3 py-1.5 text-sm text-guardian-100 hover:bg-guardian-800/60"
              title={conversation.title}
            >
              {conversation.title}
            </Link>
          ))}
        </div>
      </div>

      <div className="p-4 text-[11px] text-guardian-100/50 border-t border-guardian-800">
        Powered by the Guardian Open Platform
      </div>
    </aside>
  );
}
