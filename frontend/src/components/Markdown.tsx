import { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Source } from '../types';

/**
 * Renders assistant markdown and converts [n] citation markers into
 * clickable badges linking to the numbered Guardian source.
 */
export default function Markdown({ content, sources }: { content: string; sources: Source[] }) {
  const bySourceNumber = useMemo(() => new Map(sources.map((s) => [s.n, s])), [sources]);

  const renderWithCitations = (text: string) => {
    const parts = text.split(/(\[\d+\])/g);
    return parts.map((part, i) => {
      const match = /^\[(\d+)\]$/.exec(part);
      if (match) {
        const source = bySourceNumber.get(Number(match[1]));
        if (source) {
          const isWeb = source.type === 'web';
          return (
            <a
              key={i}
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className={isWeb ? 'citation-badge-web' : 'citation-badge'}
              title={`${isWeb ? source.source || 'Web' : 'The Guardian'}: ${source.headline}`}
            >
              {match[1]}
            </a>
          );
        }
      }
      return <span key={i}>{part}</span>;
    });
  };

  return (
    <div className="prose-chat text-[15px]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // walk text nodes to linkify [n] markers
          p: ({ children }) => <p>{mapChildren(children)}</p>,
          li: ({ children }) => <li>{mapChildren(children)}</li>,
          td: ({ children }) => <td>{mapChildren(children)}</td>,
          // wide tables scroll inside the bubble instead of widening it
          table: ({ children }) => (
            <div className="prose-chat-table">
              <table>{children}</table>
            </div>
          ),
          strong: ({ children }) => <strong>{mapChildren(children)}</strong>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );

  function mapChildren(children: React.ReactNode): React.ReactNode {
    if (typeof children === 'string') return renderWithCitations(children);
    if (Array.isArray(children)) {
      return children.map((child, i) =>
        typeof child === 'string' ? <span key={i}>{renderWithCitations(child)}</span> : child,
      );
    }
    return children;
  }
}
