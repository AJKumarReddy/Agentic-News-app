import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, NavLink, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { SECTIONS, SECTION_GROUPS } from '../constants/sections';
import Logo, { LogoMark } from './Logo';
import ThemeToggle from './ThemeToggle';
import VoiceToggle from './VoiceToggle';
import type { Theme } from '../hooks/useTheme';
import type { VoicePref } from '../hooks/useVoice';
import { deleteAllConversations, deleteConversation, listConversations, listSources } from '../services/api';
import type { ConversationSummary, NewsSourceInfo } from '../types';

export default function Sidebar({
  refreshKey,
  theme,
  onSelectTheme,
  voice,
  onSelectVoice,
  voiceAvailable,
}: {
  refreshKey?: number;
  theme: Theme;
  onSelectTheme: (theme: Theme) => void;
  voice: VoicePref;
  onSelectVoice: (voice: VoicePref) => void;
  voiceAvailable: boolean;
}) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [sources, setSources] = useState<NewsSourceInfo[]>([]);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const openConversationId = searchParams.get('conversation');
  const closeButtonRef = useRef<HTMLButtonElement>(null);

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

  // any navigation dismisses the drawer — every link inside it changes the
  // route, so this is the single close path rather than one per link
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.key]);

  useEffect(() => {
    if (!drawerOpen) return;
    closeButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDrawerOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    // the drawer scrolls on its own; the page behind it must not
    document.body.classList.add('overflow-hidden');
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.classList.remove('overflow-hidden');
    };
  }, [drawerOpen]);

  const removeOne = async (id: string) => {
    setPendingDelete(id);
    const previous = conversations;
    setConversations((prev) => prev.filter((c) => c.id !== id));
    try {
      await deleteConversation(id);
      if (openConversationId === id) navigate('/chat', { state: { newChat: Date.now() } });
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
      navigate('/chat', { state: { newChat: Date.now() } });
    } catch {
      setConversations(previous);
    }
  };

  const startNewChat = () => navigate('/chat', { state: { newChat: Date.now() } });

  const navClass = ({ isActive }: { isActive: boolean }) =>
    `flex min-h-[44px] items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors md:min-h-0 ${
      isActive ? 'bg-white/[0.08] text-white' : 'text-white/65 hover:bg-white/[0.04] hover:text-white'
    }`;

  // One body, rendered into the desktop rail and the mobile drawer. State lives
  // here in the parent, so the two copies never drift and nothing is fetched twice.
  const body = (
    <>
      {/* the logo returns to the landing screen, which is now the news rather
          than the chat — so no newChat state to carry, since the route it
          lands on never mounts ChatPage */}
      <Link
        to="/search"
        className="border-b border-white/10 px-5 py-4 transition-colors hover:bg-white/[0.04]"
      >
        <Logo />
      </Link>

      <div className="space-y-1 p-3">
        {/* search leads: it is the landing page, so the rail opens with where
            the reader already is. New chat sits under it as the way out —
            a separate "Chat" link would only duplicate this button's route. */}
        <NavLink to="/search" className={navClass}>
          Search news
        </NavLink>
        <button
          onClick={startNewChat}
          className="flex min-h-[44px] w-full items-center gap-2 rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-500 md:min-h-0"
        >
          <span className="text-base leading-none">+</span> New chat
        </button>
      </div>

      <div className="mt-1 flex-1 overflow-y-auto px-3">
        {SECTION_GROUPS.map((group) => (
          <div key={group} className="pb-2">
            <div className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-white/30">
              {group}
            </div>
            <div className="grid grid-cols-2 gap-x-1 gap-y-0.5">
              {SECTIONS.filter((s) => s.group === group).map((section) => (
                <Link
                  key={section.id}
                  to={`/search?section=${section.id}`}
                  className="flex min-h-[40px] items-center truncate rounded-md px-2.5 py-1.5 text-[13px] text-white/60 transition-colors hover:bg-white/[0.05] hover:text-white md:min-h-0 md:text-[12.5px]"
                >
                  {section.label}
                </Link>
              ))}
            </div>
          </div>
        ))}

        <div className="flex items-center justify-between px-3 pb-1.5">
          <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-white/30">
            Recent chats
          </span>
          {conversations.length > 0 && (
            <button
              onClick={removeAll}
              className="-mr-1 rounded p-1.5 text-[11px] font-medium text-white/40 transition-colors hover:text-red-300"
              title="Delete all chats"
            >
              Clear all
            </button>
          )}
        </div>
        <div className="space-y-0.5 pb-4">
          {conversations.length === 0 && (
            <div className="px-3 py-2 text-xs text-white/25">No conversations yet</div>
          )}
          {conversations.map((conversation) => (
            <div
              key={conversation.id}
              className={`group flex items-center rounded-md transition-colors ${
                openConversationId === conversation.id ? 'bg-white/[0.08]' : 'hover:bg-white/[0.04]'
              }`}
            >
              <Link
                to={`/chat?conversation=${conversation.id}`}
                className="flex min-h-[44px] min-w-0 flex-1 items-center truncate px-3 py-2 text-[13px] text-white/75 md:min-h-0"
                title={conversation.title}
              >
                {conversation.title}
              </Link>
              {/* opacity-0 until hover would make this unreachable on a
                  touchscreen, so below md it is simply always visible */}
              <button
                onClick={() => removeOne(conversation.id)}
                disabled={pendingDelete === conversation.id}
                aria-label={`Delete chat: ${conversation.title}`}
                title="Delete chat"
                className="mr-1 shrink-0 rounded p-2.5 text-white/35 transition-all hover:bg-red-500/20 hover:text-red-300 focus:opacity-100 disabled:opacity-20 md:p-1 md:opacity-0 md:group-hover:opacity-100"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 6h18M8 6V4a1 1 0 011-1h6a1 1 0 011 1v2M19 6l-1 14a1 1 0 01-1 1H7a1 1 0 01-1-1L5 6M10 11v6M14 11v6" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </div>

      <section aria-label="Settings" className="border-t border-white/10 px-3 py-3">
        <h2 className="mb-2.5 px-1 text-[10px] font-semibold uppercase tracking-[0.09em] text-white/30">
          Settings
        </h2>
        {/* roomier than the rest of the rail on purpose: these two rows are
            each a name plus a control, and at the list's spacing the names
            crowd the buttons above them */}
        <div className="space-y-3">
          <ThemeToggle theme={theme} onSelect={onSelectTheme} />
          {/* only when the backend can actually serve it — a control that
              cannot work is worse than no control */}
          {voiceAvailable && <VoiceToggle voice={voice} onSelect={onSelectVoice} />}
        </div>
      </section>

      <div className="border-t border-white/10 px-5 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] text-[10px] leading-relaxed text-white/30">
        {sources.length > 0 ? (
          <>Sourced from {sources.map((s) => s.name).join(' · ')}</>
        ) : (
          <>Sourced from leading newsrooms</>
        )}
      </div>
    </>
  );

  return (
    <>
      {/* Mobile: a top bar carries the nav the rail cannot show. Without it
          nothing below md can reach search, sections, past chats or the theme. */}
      <header className="flex shrink-0 items-center gap-1 border-b border-white/10 bg-ink-900 px-2 pt-[env(safe-area-inset-top)] text-white md:hidden">
        <button
          onClick={() => setDrawerOpen(true)}
          aria-label="Open menu"
          aria-expanded={drawerOpen}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-white/75 transition-colors hover:bg-white/[0.06] hover:text-white"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M4 7h16M4 12h16M4 17h16" />
          </svg>
        </button>

        <Link
          to="/search"
          aria-label="News AI — search the news"
          className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-1 py-2"
        >
          <LogoMark className="h-5 w-5 shrink-0" />
          <span className="truncate text-[15px] font-semibold tracking-tight">News AI</span>
        </Link>

        <button
          onClick={startNewChat}
          aria-label="New chat"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-white/75 transition-colors hover:bg-white/[0.06] hover:text-white"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
      </header>

      {/* Desktop rail — unchanged behaviour, same body */}
      <aside className="hidden w-[264px] shrink-0 flex-col border-r border-ink-800 bg-ink-900 text-white md:flex">
        {body}
      </aside>

      {/* Mobile drawer. Mounted only while open: a permanently mounted panel
          translated off-screen keeps its links in the tab order behind the page. */}
      {drawerOpen && (
        <div className="md:hidden">
          <div
            onClick={() => setDrawerOpen(false)}
            className="fixed inset-0 z-40 animate-fade-in bg-ink-900/60 backdrop-blur-[2px]"
            aria-hidden="true"
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            className="fixed inset-y-0 left-0 z-50 flex w-[86%] max-w-[300px] animate-slide-in-left flex-col bg-ink-900 pt-[env(safe-area-inset-top)] text-white shadow-2xl"
          >
            <button
              ref={closeButtonRef}
              onClick={() => setDrawerOpen(false)}
              aria-label="Close menu"
              className="absolute right-2 top-[calc(env(safe-area-inset-top)+0.75rem)] z-10 flex h-10 w-10 items-center justify-center rounded-lg text-white/60 transition-colors hover:bg-white/[0.08] hover:text-white"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
            {body}
          </aside>
        </div>
      )}
    </>
  );
}
