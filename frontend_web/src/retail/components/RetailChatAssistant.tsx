/**
 * 小売 AI アシスタント チャットUI
 * LLM Gateway を使った対話形式の売上データ分析
 * SSE ストリーミングでリアルタイム表示
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { getApiUrl } from '@/lib/url-utils';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
}

const SUGGESTED_QUESTIONS = [
  'EC業態の直近1年の売上トレンドを分析して',
  'どの業態の予測精度が最も低い？原因は？',
  'コンビニとスーパーの季節変動パターンを比較して',
  '百貨店の売上が予測を上回った月とその要因は？',
  'ドラッグストアの売上予測を改善するには？',
  '全業態の売上サマリを表にまとめて',
];

const RetailChatAssistant: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        'こんにちは！小売・EC需要予測の **AIアナリスト** です。\n\n' +
        '5業態（百貨店・スーパー・コンビニ・ドラッグストア・EC）の売上データと、' +
        'DataRobot AutoTS モデルの予測結果にアクセスできます。\n\n' +
        '売上トレンド、予測精度、誤差の原因分析など、何でもお聞きください。',
      timestamp: new Date(),
    },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // 自動スクロール
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const generateId = () => `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim() || isLoading) return;

      // ユーザーメッセージを追加
      const userMsg: ChatMessage = {
        id: generateId(),
        role: 'user',
        content: content.trim(),
        timestamp: new Date(),
      };

      const assistantMsgId = generateId();
      const assistantMsg: ChatMessage = {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setInputValue('');
      setIsLoading(true);

      // チャット履歴を構築 (welcomeメッセージを除外)
      const chatHistory = [...messages.filter((m) => m.id !== 'welcome'), userMsg].map((m) => ({
        role: m.role,
        content: m.content,
      }));

      try {
        const baseURL = getApiUrl();
        const url = new URL('retail/chat', baseURL.endsWith('/') ? baseURL : `${baseURL}/`).toString();

        abortControllerRef.current = new AbortController();

        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
          credentials: 'include',
          body: JSON.stringify({ messages: chatHistory }),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        if (!reader) throw new Error('No response body');

        let buffer = '';
        let fullContent = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const jsonStr = line.slice(6).trim();
            if (!jsonStr) continue;

            try {
              const data = JSON.parse(jsonStr);
              if (data.type === 'delta' && data.content) {
                fullContent += data.content;
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId ? { ...m, content: fullContent } : m
                  )
                );
              } else if (data.type === 'done') {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId ? { ...m, isStreaming: false } : m
                  )
                );
              } else if (data.type === 'error') {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId
                      ? { ...m, content: `エラー: ${data.message}`, isStreaming: false }
                      : m
                  )
                );
              }
            } catch {
              // skip
            }
          }
        }

        // ストリーム終了時
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantMsgId ? { ...m, isStreaming: false } : m))
        );
      } catch (error: any) {
        if (error.name === 'AbortError') return;
        console.error('[RetailChat] Error:', error);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, content: `通信エラー: ${error.message}`, isStreaming: false }
              : m
          )
        );
      } finally {
        setIsLoading(false);
        abortControllerRef.current = null;
      }
    },
    [messages, isLoading]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(inputValue);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(inputValue);
    }
  };

  const handleSuggestionClick = (question: string) => {
    sendMessage(question);
  };

  const handleStop = () => {
    abortControllerRef.current?.abort();
    setIsLoading(false);
  };

  const handleClearChat = () => {
    setMessages([
      {
        id: 'welcome',
        role: 'assistant',
        content:
          'チャット履歴をクリアしました。新しい質問をどうぞ！',
        timestamp: new Date(),
      },
    ]);
  };

  return (
    <div className="flex h-full flex-col bg-gray-900">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-700 bg-gray-800/80 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-xl">🤖</span>
          <h2 className="text-sm font-semibold text-white">小売 AI アナリスト</h2>
          <span className="rounded-full bg-green-900/50 px-2 py-0.5 text-xs text-green-400">
            オンライン
          </span>
        </div>
        <button
          onClick={handleClearChat}
          className="rounded-lg px-3 py-1.5 text-xs text-gray-400 transition-colors hover:bg-gray-700 hover:text-white"
        >
          クリア
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="mx-auto max-w-3xl space-y-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                  msg.role === 'user'
                    ? 'bg-purple-600 text-white'
                    : 'border border-gray-700 bg-gray-800 text-gray-200'
                }`}
              >
                {msg.role === 'assistant' ? (
                  <div className="prose prose-invert prose-sm max-w-none">
                    <MarkdownContent content={msg.content} />
                    {msg.isStreaming && (
                      <span className="ml-1 inline-block h-3 w-3 animate-pulse rounded-full bg-purple-400" />
                    )}
                  </div>
                ) : (
                  <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
                )}
                <p className="mt-1 text-right text-[10px] opacity-50">
                  {msg.timestamp.toLocaleTimeString('ja-JP', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </p>
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Suggested questions (show when few messages) */}
      {messages.length <= 2 && !isLoading && (
        <div className="border-t border-gray-800 bg-gray-900/50 px-4 py-3">
          <p className="mb-2 text-xs text-gray-500">質問の例:</p>
          <div className="mx-auto flex max-w-3xl flex-wrap gap-2">
            {SUGGESTED_QUESTIONS.map((q, i) => (
              <button
                key={i}
                onClick={() => handleSuggestionClick(q)}
                className="rounded-full border border-gray-700 bg-gray-800 px-3 py-1.5 text-xs text-gray-300 transition-colors hover:border-purple-500 hover:text-purple-300"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input area */}
      <div className="border-t border-gray-700 bg-gray-800/80 px-4 py-3">
        <form onSubmit={handleSubmit} className="mx-auto flex max-w-3xl items-end gap-2">
          <textarea
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="売上データについて質問してください..."
            rows={1}
            className="flex-1 resize-none rounded-xl border border-gray-600 bg-gray-700 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
            style={{ maxHeight: '120px' }}
            disabled={isLoading}
          />
          {isLoading ? (
            <button
              type="button"
              onClick={handleStop}
              className="rounded-xl bg-red-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-red-500"
            >
              停止
            </button>
          ) : (
            <button
              type="submit"
              disabled={!inputValue.trim()}
              className="rounded-xl bg-purple-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-purple-500 disabled:opacity-40"
            >
              送信
            </button>
          )}
        </form>
        <p className="mx-auto mt-1.5 max-w-3xl text-center text-[10px] text-gray-600">
          DataRobot LLM Gateway + AutoTS による分析。データは5業態の売上実績・予測を含みます。
        </p>
      </div>
    </div>
  );
};

/**
 * シンプルな Markdown → HTML 変換コンポーネント
 */
const MarkdownContent: React.FC<{ content: string }> = ({ content }) => {
  if (!content) return null;

  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeContent = '';
  let listItems: string[] = [];
  let listType: 'ul' | 'ol' | null = null;

  const flushList = () => {
    if (listItems.length > 0 && listType) {
      const Tag = listType;
      elements.push(
        <Tag key={`list-${elements.length}`} className={listType === 'ul' ? 'list-disc pl-4' : 'list-decimal pl-4'}>
          {listItems.map((item, i) => (
            <li key={i} dangerouslySetInnerHTML={{ __html: inlineFormat(item) }} />
          ))}
        </Tag>
      );
      listItems = [];
      listType = null;
    }
  };

  const inlineFormat = (text: string): string => {
    return text
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`(.+?)`/g, '<code class="bg-gray-700 px-1 rounded text-purple-300 text-xs">$1</code>');
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith('```')) {
      if (inCodeBlock) {
        elements.push(
          <pre key={`code-${i}`} className="overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs">
            <code>{codeContent}</code>
          </pre>
        );
        codeContent = '';
        inCodeBlock = false;
      } else {
        flushList();
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeContent += (codeContent ? '\n' : '') + line;
      continue;
    }

    // Headers
    if (line.startsWith('### ')) {
      flushList();
      elements.push(
        <h4 key={`h3-${i}`} className="mt-3 mb-1 text-sm font-semibold text-purple-300" dangerouslySetInnerHTML={{ __html: inlineFormat(line.slice(4)) }} />
      );
      continue;
    }
    if (line.startsWith('## ')) {
      flushList();
      elements.push(
        <h3 key={`h2-${i}`} className="mt-4 mb-2 text-base font-bold text-white" dangerouslySetInnerHTML={{ __html: inlineFormat(line.slice(3)) }} />
      );
      continue;
    }
    if (line.startsWith('# ')) {
      flushList();
      elements.push(
        <h2 key={`h1-${i}`} className="mt-4 mb-2 text-lg font-bold text-white" dangerouslySetInnerHTML={{ __html: inlineFormat(line.slice(2)) }} />
      );
      continue;
    }

    // List items
    const ulMatch = line.match(/^[-*]\s+(.+)/);
    const olMatch = line.match(/^\d+\.\s+(.+)/);
    if (ulMatch) {
      if (listType !== 'ul') flushList();
      listType = 'ul';
      listItems.push(ulMatch[1]);
      continue;
    }
    if (olMatch) {
      if (listType !== 'ol') flushList();
      listType = 'ol';
      listItems.push(olMatch[1]);
      continue;
    }

    flushList();

    // Empty line
    if (!line.trim()) {
      continue;
    }

    // Regular paragraph
    elements.push(
      <p key={`p-${i}`} className="mb-2 text-sm leading-relaxed" dangerouslySetInnerHTML={{ __html: inlineFormat(line) }} />
    );
  }

  flushList();

  return <>{elements}</>;
};

export default RetailChatAssistant;
