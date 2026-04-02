"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import { useState } from "react";
import { useLanguage } from "./LanguageContext";

interface Citation {
  id: number;
  source: string;
  original_ids: number[];
  excerpt?: string;
  content?: string;
}

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
  citations?: Citation[];
}

export default function MessageBubble({ role, content, timestamp, citations }: MessageBubbleProps) {
  const isUser = role === "user";
  const { t } = useLanguage();

  const cleanContent = content.replace(/^=+\s*$/gm, "").trim();

  const formattedTime = timestamp
    ? new Date(timestamp).toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : new Date().toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
      });

  // Convert [^N] citation markers to [N](#citation-N) links for ReactMarkdown
  // Use non-breaking space before citation to prevent orphaned citation at line start
  const processedContent = cleanContent.replace(/\s*\[\^(\d+)\]/g, "\u00A0[$1](#citation-$1)");

  // Build citation lookup map
  const citationMap = new Map<number, Citation>();
  if (citations) {
    for (const c of citations) {
      citationMap.set(c.id, c);
    }
  }

  return (
    <div className={`flex flex-col ${isUser ? "items-end" : "items-start"} mb-4`}>
      {/* Role label */}
      <div className={`flex items-center gap-1.5 mb-1 ${isUser ? "mr-2" : "ml-2"}`}>
        {isUser ? (
          <>
            <span className="text-sm">👤</span>
            <span className="text-xs font-medium text-gray-600">{t.userName}</span>
          </>
        ) : (
          <>
            <span className="text-sm">🤖</span>
            <span className="text-xs font-medium text-gray-600">{t.assistantLabel}</span>
          </>
        )}
      </div>

      {/* Message bubble */}
      <div
        className={`${
          isUser
            ? "bg-blue-600 text-white max-w-md"
            : "bg-white text-gray-800 shadow max-w-2xl"
        } rounded-2xl px-3 py-2`}
      >
        <div className={`prose prose-sm max-w-none ${isUser ? "prose-invert" : "prose-gray"} [&_ul_ul]:list-[circle] [&_ul_ul]:ml-4`}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkBreaks]}
            components={{
              // Custom link handler: render citation links as inline superscript badges
              a: (props: any) => {
                const { node, href, children, ...rest } = props;
                // Check if this is a citation link
                if (href && href.startsWith("#citation-")) {
                  const citationId = parseInt(href.replace("#citation-", ""));
                  const citation = citationMap.get(citationId);
                  return (
                    <InlineCitation
                      id={citationId}
                      source={citation?.source || `Source ${citationId}`}
                      excerpt={citation?.excerpt}
                      content={citation?.content}
                    />
                  );
                }
                // Regular link
                return (
                  <a
                    {...rest}
                    href={href || "#"}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`underline font-medium ${
                      isUser ? "text-blue-100 hover:text-white" : "text-blue-600 hover:text-blue-800"
                    }`}
                  >
                    {children}
                  </a>
                );
              },
              table: (props: any) => (
                <div className="overflow-x-auto my-4 rounded-lg border border-gray-200">
                  <table className={`min-w-full divide-y ${isUser ? "divide-blue-400 bg-blue-500" : "divide-gray-200 bg-white"}`}>
                    {props.children}
                  </table>
                </div>
              ),
              thead: (props: any) => (
                <thead className={isUser ? "bg-blue-400" : "bg-gray-50"}>{props.children}</thead>
              ),
              th: (props: any) => (
                <th className={`px-4 py-2 text-left text-xs font-medium uppercase tracking-wider ${isUser ? "text-white" : "text-gray-700"}`}>
                  {props.children}
                </th>
              ),
              tbody: (props: any) => (
                <tbody className={`${isUser ? "bg-blue-500 divide-y divide-blue-400" : "bg-white divide-y divide-gray-200"}`}>
                  {props.children}
                </tbody>
              ),
              tr: (props: any) => (
                <tr className={isUser ? "hover:bg-blue-600" : "hover:bg-gray-50"}>{props.children}</tr>
              ),
              td: (props: any) => (
                <td className={`px-4 py-2 text-sm ${isUser ? "text-white" : "text-gray-900"}`}>{props.children}</td>
              ),
              code: (props: any) => {
                const { node, inline, ...rest } = props;
                if (inline) {
                  return (
                    <code className={`px-1.5 py-0.5 rounded text-sm font-mono font-semibold ${isUser ? "bg-blue-500 text-white" : "bg-gray-100 text-purple-600"}`}>
                      {rest.children}
                    </code>
                  );
                }
                return (
                  <code className="bg-gray-900 text-gray-100 px-3 py-2 rounded-lg text-sm font-mono block overflow-x-auto">
                    {rest.children}
                  </code>
                );
              },
              pre: (props: any) => (
                <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto my-4 shadow-lg">{props.children}</pre>
              ),
              img: (props: any) => {
                const { node, ...rest } = props;
                return <img {...rest} src={rest.src || ""} alt={rest.alt || "Image"} className="rounded-lg shadow-md max-w-full h-auto my-4 border border-gray-200" loading="lazy" />;
              },
              h1: (props: any) => (<h1 className={`text-xl font-bold mt-4 mb-2 ${isUser ? "text-white" : "text-gray-900"}`} {...props}>{props.children}</h1>),
              h2: (props: any) => (<h2 className={`text-lg font-bold mt-3 mb-2 ${isUser ? "text-white" : "text-gray-900"}`} {...props}>{props.children}</h2>),
              h3: (props: any) => (<h3 className={`text-base font-bold mt-2 mb-1 ${isUser ? "text-white" : "text-gray-900"}`} {...props}>{props.children}</h3>),
              h4: (props: any) => (<h4 className={`text-sm font-bold mt-2 mb-1 ${isUser ? "text-white" : "text-gray-900"}`} {...props}>{props.children}</h4>),
              p: (props: any) => (<p className={`my-2 leading-relaxed ${isUser ? "text-white" : "text-gray-800"}`} {...props}>{props.children}</p>),
              strong: (props: any) => (<strong className={`font-bold ${isUser ? "text-white" : "text-gray-900"}`} {...props}>{props.children}</strong>),
              em: (props: any) => (<em className={`italic ${isUser ? "text-white" : "text-gray-800"}`} {...props}>{props.children}</em>),
              ol: (props: any) => (<ol className="list-decimal list-inside my-3 space-y-1 ml-4" {...props}>{props.children}</ol>),
              ul: (props: any) => (<ul className="list-disc list-inside my-2 space-y-1 ml-4" {...props}>{props.children}</ul>),
              li: (props: any) => (<li className={`leading-relaxed ${isUser ? "text-white" : "text-gray-800"}`} {...props}>{props.children}</li>),
              blockquote: (props: any) => (
                <blockquote className={`border-l-4 pl-4 my-4 italic ${isUser ? "border-blue-400 text-blue-50" : "border-gray-300 text-gray-700"}`} {...props}>{props.children}</blockquote>
              ),
              hr: (props: any) => (<hr className={`my-4 ${isUser ? "border-blue-400" : "border-gray-300"}`} {...props} />),
              div: (props: any) => <div {...props}>{props.children}</div>,
              span: (props: any) => <span {...props}>{props.children}</span>,
            }}
          >
            {processedContent}
          </ReactMarkdown>
        </div>
      </div>

      {/* Timestamp */}
      <div className={`text-xs text-gray-400 mt-1 ${isUser ? "mr-2" : "ml-2"}`}>
        {formattedTime}
      </div>
    </div>
  );
}

/** Inline citation badge rendered as superscript with hover tooltip */
function InlineCitation({ id, source, excerpt, content }: { id: number; source: string; excerpt?: string; content?: string }) {
  const [showTooltip, setShowTooltip] = useState(false);

  // Use content (source document excerpt) if available, otherwise fall back to excerpt
  const tooltipContent = content || excerpt;

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <span
        className="inline-flex items-center justify-center
                   w-4 h-4 rounded-full text-[10px] font-bold leading-none
                   bg-gray-500 text-white cursor-help
                   hover:bg-gray-600 transition-colors
                   align-super ml-0.5 mr-0.5"
      >
        {id}
      </span>
      {showTooltip && (
        <span
          className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2
                     px-4 py-2.5 rounded-lg bg-gray-900 text-white text-xs
                     max-w-md whitespace-normal z-50 shadow-lg
                     text-left font-normal min-w-48"
        >
          <span className="font-semibold text-white">{source}</span>
          {tooltipContent && (
            <span className="block mt-1 text-gray-300 text-[11px] leading-relaxed border-t border-gray-700 pt-1 max-h-40 overflow-y-auto">
              {tooltipContent}
            </span>
          )}
          <span
            className="absolute top-full left-1/2 -translate-x-1/2
                       border-4 border-transparent border-t-gray-900"
          />
        </span>
      )}
    </span>
  );
}
