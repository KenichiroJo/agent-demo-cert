/**
 * AI 誤差分析パネル
 * 予測誤差の分析結果とVDB検索結果を表示
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
      <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-6">
        <h3 className="mb-4 text-lg font-semibold text-white">AI 分析実行中...</h3>
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-purple-500 border-t-transparent" />
          <p className="text-sm text-gray-400">
            {progressMessage || '予測誤差を分析し、根拠となるデータを収集しています...'}
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-700 bg-red-900/20 p-4">
        <p className="text-red-400">{error}</p>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="rounded-xl border border-blue-700/30 bg-blue-900/10 p-4">
        <div className="flex items-start gap-3">
          <span className="text-xl">💡</span>
          <p className="text-sm text-blue-300">
            チャート上の任意のデータポイントをクリックすると、AI による予測誤差の
            根本原因分析を実行できます。季節変動、消費者動向、外部経済要因などを
            考慮した分析結果が表示されます。
          </p>
        </div>
      </div>
    );
  }

  const generateMarkdownReport = () => {
    let report = '';
    report += analysis.analysis?.summary || analysis.hypothesis || '';
    report += '\n\n';

    if (analysis.rmse_context) {
      report += '---\n\n### 誤差コンテキスト\n\n';
      const ctx = analysis.rmse_context;
      if (ctx.store_type_rmse != null) report += `- 業態 RMSE: **${Number(ctx.store_type_rmse).toFixed(1)}億円**\n`;
      if (ctx.store_type_mae != null) report += `- 業態 MAE: **${Number(ctx.store_type_mae).toFixed(1)}億円**\n`;
      if (ctx.overall_percentile != null) report += `- 全体パーセンタイル: **上位 ${Number(ctx.overall_percentile).toFixed(0)}%**\n`;
      if (ctx.z_score != null) report += `- Z スコア: **${Number(ctx.z_score).toFixed(2)}**\n`;
      report += '\n';
    }

    if (analysis.analysis?.vdb_reports?.length) {
      report += '---\n\n### 関連市場レポート（VDB検索結果）\n\n';
      analysis.analysis.vdb_reports.forEach((r: string, i: number) => { report += `${i + 1}. ${r}\n\n`; });
    }

    if (analysis.recommendations?.length) {
      report += '---\n\n### 推奨アクション\n\n';
      analysis.recommendations.forEach((rec: string, i: number) => { report += `${i + 1}. ${rec}\n`; });
      report += '\n';
    }

    return report;
  };

  return (
    <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-4 shadow-lg">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">AI 誤差分析レポート</h2>
        {analysis.confidence_score != null && (
          <span className="rounded-full bg-purple-900/50 px-3 py-1 text-xs font-medium text-purple-300">
            信頼度: {(analysis.confidence_score * 100).toFixed(0)}%
          </span>
        )}
      </div>

      <div className="mb-4 rounded-lg bg-gray-700/30 p-3">
        <div className="grid grid-cols-3 gap-4 text-center text-sm">
          <div>
            <p className="text-gray-400">業態</p>
            <p className="font-medium text-white">{analysis.store_type}</p>
          </div>
          <div>
            <p className="text-gray-400">日付</p>
            <p className="font-medium text-white">{new Date(analysis.date).toLocaleDateString('ja-JP')}</p>
          </div>
          <div>
            <p className="text-gray-400">予測誤差</p>
            <p className={`font-medium ${Math.abs(analysis.error) > 5 ? 'text-red-400' : 'text-green-400'}`}>
              {analysis.error > 0 ? '+' : ''}{analysis.error.toFixed(1)}億円
            </p>
          </div>
        </div>
      </div>

      <div className="prose prose-sm prose-invert max-h-[500px] overflow-y-auto rounded-lg border border-gray-600 bg-gray-900/50 p-4 text-[14px] leading-relaxed" style={{ scrollbarWidth: 'thin' }}>
        <ReactMarkdown>{generateMarkdownReport()}</ReactMarkdown>
      </div>
    </div>
  );
};

export default ExplainabilityPanel;
