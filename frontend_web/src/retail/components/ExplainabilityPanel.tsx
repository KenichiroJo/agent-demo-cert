/**
 * AI 誤差分析パネル
 * LLM Gateway からの分析結果をリッチに表示
 */

import React from 'react';
import ReactMarkdown from 'react-markdown';
import type { ErrorAnalysisResponse } from '../services/api';

interface ExplainabilityPanelProps {
  analysis: ErrorAnalysisResponse | null;
  loading?: boolean;
  error?: string | null;
  progressMessage?: string;
}

const ExplainabilityPanel: React.FC<ExplainabilityPanelProps> = ({
  analysis,
  loading = false,
  error = null,
  progressMessage = '',
}) => {
  if (loading) {
    return (
      <div className="rounded-xl border border-purple-700/50 bg-gray-800/50 p-6">
        <h3 className="mb-4 text-lg font-semibold text-white">🤖 AI 分析実行中...</h3>
        <div className="flex flex-col items-center gap-4">
          <div className="relative h-12 w-12">
            <div className="absolute inset-0 animate-spin rounded-full border-2 border-purple-500 border-t-transparent" />
            <div className="absolute inset-2 animate-ping rounded-full bg-purple-500/20" />
          </div>
          <p className="text-sm text-gray-400">
            {progressMessage || 'DataRobot LLM Gateway で予測誤差の根本原因を分析しています...'}
          </p>
          <div className="w-full max-w-xs overflow-hidden rounded-full bg-gray-700">
            <div className="h-1 animate-pulse rounded-full bg-gradient-to-r from-purple-500 to-blue-500" style={{ width: '60%' }} />
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-700 bg-red-900/20 p-4">
        <p className="text-red-400">❌ {error}</p>
      </div>
    );
  }

  if (!analysis) {
    return null;
  }

  const absPctError = Math.abs((analysis.error / (analysis.actual_sales || 1)) * 100);
  const errorDirection = analysis.error > 0 ? '過小予測' : '過大予測';
  const errorSeverity =
    absPctError > 10 ? 'text-red-400' : absPctError > 5 ? 'text-yellow-400' : 'text-green-400';

  return (
    <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-4 shadow-lg">
      {/* ヘッダー */}
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">🤖 AI 誤差分析レポート</h2>
        {analysis.confidence_score != null && (
          <span
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              analysis.confidence_score > 0.7
                ? 'bg-green-900/50 text-green-300'
                : analysis.confidence_score > 0.5
                  ? 'bg-yellow-900/50 text-yellow-300'
                  : 'bg-red-900/50 text-red-300'
            }`}
          >
            分析信頼度: {(analysis.confidence_score * 100).toFixed(0)}%
          </span>
        )}
      </div>

      {/* サマリーカード */}
      <div className="mb-4 rounded-lg bg-gradient-to-r from-gray-700/50 to-gray-700/30 p-4">
        <div className="grid grid-cols-4 gap-4 text-center text-sm">
          <div>
            <p className="text-xs text-gray-400">業態</p>
            <p className="mt-1 font-semibold text-white">{analysis.store_type}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400">対象月</p>
            <p className="mt-1 font-semibold text-white">
              {new Date(analysis.date).toLocaleDateString('ja-JP', { year: 'numeric', month: 'long' })}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400">予測誤差</p>
            <p className={`mt-1 font-semibold ${errorSeverity}`}>
              {analysis.error > 0 ? '+' : ''}
              {analysis.error.toFixed(2)}億円
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400">誤差方向</p>
            <p className={`mt-1 font-semibold ${errorSeverity}`}>{errorDirection}</p>
          </div>
        </div>

        {/* 実績 vs 予測バー */}
        <div className="mt-3 flex items-center gap-2 text-xs">
          <span className="text-orange-400">実績: {analysis.actual_sales.toFixed(2)}億円</span>
          <div className="flex-1 h-2 rounded-full bg-gray-600 overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-orange-400 to-orange-500"
              style={{
                width: `${Math.min(100, (analysis.actual_sales / Math.max(analysis.actual_sales, analysis.predicted_sales)) * 100)}%`,
              }}
            />
          </div>
          <span className="text-purple-400">予測: {analysis.predicted_sales.toFixed(2)}億円</span>
        </div>
      </div>

      {/* 統計コンテキスト（コンパクト） */}
      {analysis.rmse_context && (
        <div className="mb-4 flex flex-wrap gap-2">
          {analysis.rmse_context.store_type_rmse != null && (
            <span className="rounded-full bg-gray-700/50 px-2 py-1 text-xs text-gray-300">
              RMSE: {Number(analysis.rmse_context.store_type_rmse).toFixed(2)}億円
            </span>
          )}
          {analysis.rmse_context.store_type_mae != null && (
            <span className="rounded-full bg-gray-700/50 px-2 py-1 text-xs text-gray-300">
              MAE: {Number(analysis.rmse_context.store_type_mae).toFixed(2)}億円
            </span>
          )}
          {analysis.rmse_context.overall_percentile != null && (
            <span className="rounded-full bg-gray-700/50 px-2 py-1 text-xs text-gray-300">
              パーセンタイル: 上位{Number(analysis.rmse_context.overall_percentile).toFixed(0)}%
            </span>
          )}
          {analysis.rmse_context.z_score != null && (
            <span className="rounded-full bg-gray-700/50 px-2 py-1 text-xs text-gray-300">
              Z: {Number(analysis.rmse_context.z_score).toFixed(2)}
            </span>
          )}
        </div>
      )}

      {/* LLM 分析本文 */}
      <div
        className="prose prose-sm prose-invert max-w-none overflow-y-auto rounded-lg border border-gray-600 bg-gray-900/50 p-5 text-[14px] leading-relaxed"
        style={{ maxHeight: '600px', scrollbarWidth: 'thin' }}
      >
        <ReactMarkdown
          components={{
            h1: ({ children }) => <h2 className="mt-4 mb-2 text-lg font-bold text-purple-300">{children}</h2>,
            h2: ({ children }) => <h3 className="mt-3 mb-2 text-base font-semibold text-purple-300">{children}</h3>,
            h3: ({ children }) => <h4 className="mt-2 mb-1 text-sm font-semibold text-blue-300">{children}</h4>,
            strong: ({ children }) => <strong className="text-white">{children}</strong>,
            li: ({ children }) => <li className="my-1 text-gray-300">{children}</li>,
            p: ({ children }) => <p className="my-2 text-gray-300">{children}</p>,
            hr: () => <hr className="my-3 border-gray-600" />,
          }}
        >
          {analysis.analysis?.summary || '分析結果がありません。'}
        </ReactMarkdown>
      </div>

      {/* フッター */}
      <div className="mt-3 flex items-center justify-between text-xs text-gray-500">
        <span>Powered by DataRobot LLM Gateway + AutoTS</span>
        <span>
          {new Date().toLocaleString('ja-JP', { hour: '2-digit', minute: '2-digit' })} 生成
        </span>
      </div>
    </div>
  );
};

export default ExplainabilityPanel;
