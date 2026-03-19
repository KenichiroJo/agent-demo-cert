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
    <div className="flex h-full w-full bg-gray-900">
      {/* Left sidebar: info + suggestions */}
      <div className="hidden w-72 flex-shrink-0 flex-col border-r border-gray-700 bg-gray-800/60 lg:flex">
        {/* Sidebar header */}
        <div className="border-b border-gray-700 px-4 py-4">
          <div className="flex items-center gap-2">
            <span className="text-2xl">🤖</span>
            <div>
              <h2 className="text-sm font-bold text-white">小売 AI アナリスト</h2>
              <p className="text-[11px] text-gray-500">DataRobot LLM Gateway</p>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-green-500" />
            <span className="text-xs text-green-400">オンライン</span>
          </div>
        </div>

        {/* Capabilities */}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">分析可能な項目</p>
          <div className="space-y-2">
            {[
              { icon: '📊', label: '売上トレンド分析' },
              { icon: '🎯', label: '予測精度の評価' },
              { icon: '🔍', label: '誤差の根本原因' },
              { icon: '📅', label: '季節変動パターン' },
              { icon: '🏪', label: '業態間の比較' },
              { icon: '💡', label: '改善アクション提案' },
            ].map(({ icon, label }) => (
              <div key={label} className="flex items-center gap-2 rounded-lg bg-gray-800/50 px-3 py-2">
                <span className="text-sm">{icon}</span>
                <span className="text-xs text-gray-300">{label}</span>
              </div>
            ))}
          </div>

          <p className="mb-3 mt-6 text-xs font-semibold uppercase tracking-wider text-gray-500">対象業態</p>
          <div className="flex flex-wrap gap-1.5">
            {['百貨店', 'スーパー', 'コンビニ', 'ドラッグストア', 'EC'].map((st) => (
              <span key={st} className="rounded-full border border-purple-800/50 bg-purple-900/20 px-2.5 py-1 text-[11px] text-purple-300">
                {st}
              </span>
            ))}
          </div>

          {/* Quick questions */}
          <p className="mb-3 mt-6 text-xs font-semibold uppercase tracking-wider text-gray-500">クイック質問</p>
          <div className="space-y-1.5">
            {SUGGESTED_QUESTIONS.map((q, i) => (
              <button
                key={i}
                onClick={() => handleSuggestionClick(q)}
                disabled={isLoading}
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-left text-xs text-gray-300 transition-colors hover:border-purple-500 hover:text-purple-300 disabled:opacity-50"
              >
                {q}
              </button>
            ))}
          </div>
        </div>

        {/* Sidebar footer */}
        <div className="border-t border-gray-700 px-4 py-3">
          <button
            onClick={handleClearChat}
            className="w-full rounded-lg border border-gray-600 bg-gray-700 px-3 py-2 text-xs text-gray-300 transition-colors hover:bg-gray-600 hover:text-white"
          >
            会話をクリア
          </button>
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex flex-1 flex-col">
        {/* Mobile header (visible on small screens) */}
        <div className="flex items-center justify-between border-b border-gray-700 bg-gray-800/80 px-4 py-2.5 lg:hidden">
          <div className="flex items-center gap-2">
            <span>🤖</span>
            <span className="text-sm font-semibold text-white">小売 AI アナリスト</span>
            <span className="h-2 w-2 rounded-full bg-green-500" />
          </div>
          <button onClick={handleClearChat} className="text-xs text-gray-400 hover:text-white">クリア</button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="space-y-5">
            {messages.map((msg) => (
              <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                {/* Avatar */}
                <div className={`flex-shrink-0 ${msg.role === 'user' ? 'ml-2' : 'mr-2'}`}>
                  <div className={`flex h-8 w-8 items-center justify-center rounded-full text-sm ${
                    msg.role === 'user' ? 'bg-purple-600' : 'bg-gray-700'
                  }`}>
                    {msg.role === 'user' ? '👤' : '🤖'}
                  </div>
                </div>
                {/* Message bubble */}
                <div className={`min-w-0 flex-1 ${msg.role === 'user' ? 'max-w-[70%] ml-auto' : ''}`}>
                  <div className={`rounded-2xl px-5 py-3.5 ${
                    msg.role === 'user'
                      ? 'bg-purple-600 text-white'
                      : 'border border-gray-700 bg-gray-800/80 text-gray-200'
                  }`}>
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
                  </div>
                  <p className={`mt-1 text-[10px] text-gray-600 ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>
                    {msg.timestamp.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Suggested questions (inline, show when few messages on mobile) */}
        {messages.length <= 2 && !isLoading && (
          <div className="border-t border-gray-800 bg-gray-900/50 px-6 py-3 lg:hidden">
            <div className="flex flex-wrap gap-2">
              {SUGGESTED_QUESTIONS.slice(0, 4).map((q, i) => (
                <button
                  key={i}
                  onClick={() => handleSuggestionClick(q)}
                  className="rounded-full border border-gray-700 bg-gray-800 px-3 py-1.5 text-xs text-gray-300 hover:border-purple-500 hover:text-purple-300"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Input area */}
        <div className="border-t border-gray-700 bg-gray-800/80 px-6 py-4">
          <form onSubmit={handleSubmit} className="flex items-end gap-3">
            <textarea
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="売上データについて質問してください... (Shift+Enter で改行)"
              rows={1}
              className="flex-1 resize-none rounded-xl border border-gray-600 bg-gray-700 px-4 py-3 text-sm text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
              style={{ maxHeight: '120px' }}
              disabled={isLoading}
            />
            {isLoading ? (
              <button
                type="button"
                onClick={handleStop}
                className="rounded-xl bg-red-600 px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-red-500"
              >
                停止
              </button>
            ) : (
              <button
                type="submit"
                disabled={!inputValue.trim()}
                className="rounded-xl bg-purple-600 px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-purple-500 disabled:opacity-40"
              >
                送信
              </button>
            )}
          </form>
        </div>
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
