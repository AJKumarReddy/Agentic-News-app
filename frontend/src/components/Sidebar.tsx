import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, NavLink, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { SECTIONS } from '../constants/sections';
import Logo, { LogoMark } from './Logo';
import SageAvatar from './SageAvatar';
import ThemeToggle from './ThemeToggle';
import VoiceToggle from './VoiceToggle';
import type { Theme } from '../hooks/useTheme';
import type { VoicePref } from '../hooks/useVoice';
import { deleteAllConversations, deleteConversation, listConversations } from '../services/api';
import type { ConversationSummary } from '../types';
import { readStored, writeStored } from '../utils/storage';

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
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  // closed by default: two controls a reader sets once should not spend
  // rail height on every screen forever
  // the whole rail, hidden — remembered, because someone who wants the
  // articles full-width wants that on every visit, not just this one
  const [railCollapsed, setRailCollapsed] = useState(() => readStored('rail-collapsed') === 'yes');
  const [settingsOpen, setSettingsOpen] = useState(() => readStored('settings-open') === 'yes');
  // remembered: a reader who collapses this does not want it back every visit
  const [sectionsOpen, setSectionsOpen] = useState(() => readStored('sections-open') !== 'no');
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

  useEffect(() => writeStored('rail-collapsed', railCollapsed ? 'yes' : 'no'), [railCollapsed]);
  useEffect(() => writeStored('sections-open', sectionsOpen ? 'yes' : 'no'), [sectionsOpen]);
  useEffect(() => writeStored('settings-open', settingsOpen ? 'yes' : 'no'), [settingsOpen]);

  useEffect(load, [load, refreshKey]);
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

  // One row shape for everything in the rail. Nav rows and section rows used
  // to differ in height, size and padding, which is most of why the rail read
  // as assembled rather than designed.
  const rowClass = (active: boolean) =>
    `flex min-h-[40px] items-center gap-2.5 rounded-lg px-3 text-[13.5px] transition-colors md:min-h-[34px] ${
      active
        ? 'bg-white/[0.09] font-medium text-white'
        : 'text-white/60 hover:bg-white/[0.05] hover:text-white'
    }`;
  const navClass = ({ isActive }: { isActive: boolean }) => rowClass(isActive);

  // the section the rail should show as current, and only while on /search
  const activeSection =
    location.pathname === '/search' ? searchParams.get('section') ?? '' : '';

  // One body, rendered into the desktop rail and the mobile drawer. State lives
  // here in the parent, so the two copies never drift and nothing is fetched twice.
  const body = (
    <>
      {/* the logo returns to the landing screen, which is now the news rather
          than the chat — so no newChat state to carry, since the route it
          lands on never mounts ChatPage */}
      <div className="flex items-center border-b border-white/10 pr-2">
        <Link to="/search" className="min-w-0 flex-1 px-5 py-4 transition-colors hover:bg-white/[0.04]">
          <Logo />
        </Link>
        {/* desktop only: below md the rail is already a drawer with its own
            close, and hiding it there would leave nothing to navigate by */}
        <button
          onClick={() => setRailCollapsed(true)}
          aria-label="Collapse menu"
          className="hidden h-9 w-9 shrink-0 items-center justify-center rounded-lg text-white/50 transition-colors hover:bg-white/[0.08] hover:text-white md:flex"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 6l-6 6 6 6" />
          </svg>
        </button>
      </div>

      <div className="space-y-1 p-3">
        {/* Two controls used to promise the same thing: this one, styled as
            the primary action, and the floating Ask Sage button — which is
            the better path, since it answers over the page you are reading
            instead of navigating away from it. So the FAB keeps the weight
            and this is a plain link to the full view, where a long thread and
            its history belong. */}
        <NavLink to="/search" end className={navClass}>
          <svg className="h-[18px] w-[18px] shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          Search news
        </NavLink>
        <NavLink to="/chat" state={{ newChat: Date.now() }} className={navClass}>
          <SageAvatar className="h-[18px] w-[18px] shrink-0" />
          Chat
        </NavLink>
      </div>

      <div className="mt-1 flex-1 overflow-y-auto px-3">
        {/* A single column, not the two-column grid this was: a grid of links
            reads as a footer sitemap, where every rail in every app people
            already use is a list of rows. Collapsible because ten desks is
            most of the rail's height for someone who navigates by search. */}
        <div className="pb-2">
          <button
            onClick={() => setSectionsOpen((wasOpen) => !wasOpen)}
            aria-expanded={sectionsOpen}
            className="flex w-full items-center gap-1 rounded-md px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-[0.09em] text-white/50 transition-colors hover:text-white/80"
          >
            Sections
            <svg
              className={`h-3.5 w-3.5 transition-transform ${sectionsOpen ? '' : '-rotate-90'}`}
              viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
            >
              <path d="m6 9 6 6 6-6" />
            </svg>
          </button>
          {sectionsOpen && (
            <div className="space-y-0.5">
              {SECTIONS.map((section) => (
                <Link
                  key={section.id}
                  to={`/search?section=${section.id}`}
                  aria-current={activeSection === section.id ? 'page' : undefined}
                  className={rowClass(activeSection === section.id)}
                >
                  {section.label}
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between px-3 pb-1.5">
          <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-white/50">
            Recent chats
          </span>
          {conversations.length > 0 && (
            <button
              onClick={removeAll}
              className="-mr-1 rounded p-1.5 text-[11px] font-medium text-white/50 transition-colors hover:text-red-300"
              title="Delete all chats"
            >
              Clear all
            </button>
          )}
        </div>
        <div className="space-y-0.5 pb-4">
          {conversations.length === 0 && (
            <div className="px-3 py-2 text-xs text-white/50">No conversations yet</div>
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
                className="mr-1 shrink-0 rounded p-2.5 text-white/50 transition-all hover:bg-red-500/20 hover:text-red-300 focus:opacity-100 disabled:opacity-20 md:p-1 md:opacity-0 md:group-hover:opacity-100"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 6h18M8 6V4a1 1 0 011-1h6a1 1 0 011 1v2M19 6l-1 14a1 1 0 01-1 1H7a1 1 0 01-1-1L5 6M10 11v6M14 11v6" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Same disclosure as Sections, so the rail has one idea of what a
          group is. Collapsed by default and pinned rather than scrolling with
          the conversation list: these are set once, but when someone does want
          them they should not have to hunt past a long history to find them. */}
      <section className="border-t border-white/10 px-3 py-2">
        <button
          onClick={() => setSettingsOpen((wasOpen) => !wasOpen)}
          aria-expanded={settingsOpen}
          className="flex w-full items-center gap-1 rounded-md px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.09em] text-white/50 transition-colors hover:text-white/80"
        >
          Settings
          <svg
            className={`h-3.5 w-3.5 transition-transform ${settingsOpen ? '' : '-rotate-90'}`}
            viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
          >
            <path d="m6 9 6 6 6-6" />
          </svg>
        </button>
        {settingsOpen && (
          <div className="space-y-3 px-1 pb-1 pt-2.5">
            <ThemeToggle theme={theme} onSelect={onSelectTheme} />
            {/* only when the backend can actually serve it — a control that
                cannot work is worse than no control */}
            {voiceAvailable && <VoiceToggle voice={voice} onSelect={onSelectVoice} />}
          </div>
        )}
      </section>

      <div className="border-t border-white/10 px-5 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] text-[10px] leading-relaxed text-white/50">
        <span className="mb-2 flex items-center gap-1.5">
          <SageAvatar className="h-5 w-5 shrink-0" />
          <span className="text-[11px] text-white/55">
            Powered by <span className="font-semibold text-white/80">Sage</span>
          </span>
        </span>
        {/* deliberately names nobody: the roster is whichever API keys are
            configured, and one of them relays hundreds of newsrooms under a
            single id — so any list here is either stale or misleading. Each
            article carries its own publisher on its card and in its citation,
            which is where the attribution actually belongs. */}
        Sourced from leading newsrooms
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
          aria-label="Source — search the news"
          className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-1 py-2"
        >
          <LogoMark className="h-5 w-5 shrink-0" />
          <span className="truncate text-[15px] font-semibold tracking-tight">Source</span>
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
      {railCollapsed ? (
        /* A slim column, not a floating button. Fixed-positioned it sat on top
           of the page heading, because a fixed element takes no layout space —
           the content had no idea it was there. This keeps its 48px in the
           flex row, so the articles start after it like they do after the
           full rail. */
        <aside className="hidden w-12 shrink-0 flex-col items-center border-r border-ink-800 bg-ink-900 py-3 md:flex">
          <button
            onClick={() => setRailCollapsed(false)}
            aria-label="Show menu"
            aria-expanded={false}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-white/60 transition-colors hover:bg-white/[0.08] hover:text-white"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
              <path d="M4 7h16M4 12h16M4 17h16" />
            </svg>
          </button>
        </aside>
      ) : (
        <aside className="hidden w-[264px] shrink-0 flex-col border-r border-ink-800 bg-ink-900 text-white md:flex">
          {body}
        </aside>
      )}

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
