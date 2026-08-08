import { useCallback, useRef, useState } from 'react';
import { streamChat } from '../services/api';
import type { ChatMessage } from '../types';

export function useChat(initialConversationId?: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(initialConversationId ?? null);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (text: string, articleId?: string | null) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;
      setBusy(true);
      setMessages((prev) => [
        ...prev,
        { role: 'user', content: trimmed, sources: [] },
        { role: 'assistant', content: '', sources: [], streaming: true, status: 'Thinking…' },
      ]);

      const controller = new AbortController();
      abortRef.current = controller;

      const updateAssistant = (updater: (m: ChatMessage) => ChatMessage) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === 'assistant') next[next.length - 1] = updater(last);
          return next;
        });
      };

      try {
        await streamChat(trimmed, {
          conversationId,
          articleId,
          signal: controller.signal,
          onEvent: (event) => {
            switch (event.type) {
              case 'state':
                setConversationId(event.conversation_id);
                break;
              case 'status':
                updateAssistant((m) => ({ ...m, status: event.detail }));
                break;
              case 'token':
                updateAssistant((m) => ({ ...m, status: undefined, content: m.content + event.delta }));
                break;
              case 'sources':
                updateAssistant((m) => ({ ...m, sources: event.sources }));
                break;
              case 'error':
                updateAssistant((m) => ({
                  ...m,
                  status: undefined,
                  streaming: false,
                  content: m.content || `⚠️ ${event.detail}`,
                }));
                break;
              case 'done':
                updateAssistant((m) => ({ ...m, status: undefined, streaming: false }));
                break;
            }
          },
        });
      } catch (error) {
        if (!controller.signal.aborted) {
          updateAssistant((m) => ({
            ...m,
            status: undefined,
            streaming: false,
            content: m.content || '⚠️ Could not reach the assistant. Check that the backend is running.',
          }));
        }
      } finally {
        updateAssistant((m) => ({ ...m, status: undefined, streaming: false }));
        setBusy(false);
      }
    },
    [busy, conversationId],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setConversationId(null);
    setBusy(false);
  }, []);

  return { messages, setMessages, conversationId, setConversationId, busy, send, stop, reset };
}
