/**
 * メインダッシュボードコンポーネント
 * 業態セレクター、日付フィルター、KPIバッジ、チャート、分析パネル、PDF出力
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import ForecastChart from './ForecastChart';
import ExplainabilityPanel from './ExplainabilityPanel';
import retailApiService, {
  type ForecastData,
  type ErrorAnalysisResponse,
} from '../services/api';
import { exportDashboardPdf } from '../utils/exportPdf';

const ForecastDashboard: React.FC = () => {
  const [selectedStoreType, setSelectedStoreType] = useState<string>('');
  const [storeTypes, setStoreTypes] = useState<string[]>([]);
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [minDate, setMinDate] = useState<string>('');
  const [maxDate, setMaxDate] = useState<string>('');
  const [forecastData, setForecastData] = useState<ForecastData[]>([]);
  const [analysis, setAnalysis] = useState<ErrorAnalysisResponse | null>(null);
  const [loading, setLoading] = useState({ data: false, analysis: false, init: true });
  const [error, setError] = useState<string | null>(null);
  const [analysisProgress, setAnalysisProgress] = useState<string>('');
  const [exporting, setExporting] = useState(false);

  // Refs for PDF export
  const chartRef = useRef<HTMLDivElement>(null);
  const analysisRef = useRef<HTMLDivElement>(null);

  // Initialize
  useEffect(() => {
    const init = async () => {
      setLoading((prev) => ({ ...prev, init: true }));
      try {
        const types = await retailApiService.getStoreTypes();
        setStoreTypes(types);
        if (types.length > 0) {
          setSelectedStoreType(types[0]);
        }

        const dateRange = await retailApiService.getDateRange();
        const start = (dateRange.start_date || '').split('T')[0];
        const end = (dateRange.end_date || '').split('T')[0];

        if (!start || !end) {
          setError('日付範囲の取得に失敗しました。データが存在するか確認してください。');
          return;
        }

        setMinDate(start);
        setMaxDate(end);

        // Default: last 1 year
        const endD = new Date(end);
        const startD = new Date(endD);
        startD.setFullYear(startD.getFullYear() - 1);
        const defaultStart = startD.toISOString().split('T')[0];
        setStartDate(defaultStart > start ? defaultStart : start);
        setEndDate(end);
      } catch (err: any) {
        console.error('Dashboard init error:', err);
        setError(err?.response?.data?.detail || err?.message || '初期化に失敗しました');
      } finally {
        setLoading((prev) => ({ ...prev, init: false }));
      }
    };
    init();
  }, []);

  // Fetch data when filters change (debounced)
  useEffect(() => {
    if (!selectedStoreType || !startDate || !endDate) return;
    if (startDate.length < 10 || endDate.length < 10) return;
    const timer = setTimeout(() => {
      fetchData();
    }, 400);
    return () => clearTimeout(timer);
  }, [selectedStoreType, startDate, endDate]);

  const fetchData = useCallback(async () => {
    setLoading((prev) => ({ ...prev, data: true }));
    setError(null);
    try {
      const data = await retailApiService.getForecastData({
        store_type: selectedStoreType,
        start_date: startDate,
        end_date: endDate,
      });
      setForecastData(data);
    } catch (err: any) {
      console.error('Fetch error:', err);
      setError(err?.response?.data?.detail || err?.message || 'データ取得に失敗しました');
    } finally {
      setLoading((prev) => ({ ...prev, data: false }));
    }
  }, [selectedStoreType, startDate, endDate]);

  const handleAnalyzeError = useCallback(async (point: ForecastData) => {
    console.log('[Dashboard] handleAnalyzeError called:', {
      store_type: point.store_type,
      date: point.date,
      predicted_sales: point.predicted_sales,
    });

    setLoading((prev) => ({ ...prev, analysis: true }));
    setAnalysis(null);
    setAnalysisProgress('分析を開始しています...');

    try {
      console.log('[Dashboard] Calling analyzeError API...');
      const result = await retailApiService.analyzeError(
        { store_type: point.store_type, date: point.date },
        (status: string, elapsed?: number) => {
          console.log('[Dashboard] SSE progress:', status, elapsed);
          if (status === 'started') setAnalysisProgress('AI 分析エージェントを呼び出し中...');
          else if (status === 'processing') setAnalysisProgress(`処理中... (${elapsed}秒経過)`);
        }
      );
      console.log('[Dashboard] Analysis complete:', result?.store_type, result?.date);
      setAnalysis(result);
      setAnalysisProgress('');
    } catch (err: any) {
      console.error('[Dashboard] Analysis error:', err);
      setAnalysisProgress('');
      setError(err?.message || '分析に失敗しました');
    } finally {
      setLoading((prev) => ({ ...prev, analysis: false }));
    }
  }, []);

  const handleExportPdf = useCallback(async () => {
    setExporting(true);
    try {
      await exportDashboardPdf(chartRef.current, analysisRef.current, {
        storeType: selectedStoreType,
        startDate,
        endDate,
      });
    } catch (err: any) {
      console.error('[PDF] Export error:', err);
      setError('PDF出力に失敗しました: ' + err?.message);
    } finally {
      setExporting(false);
    }
  }, [selectedStoreType, startDate, endDate]);

  if (loading.init) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-purple-500 border-t-transparent" />
          <p className="text-gray-400">ダッシュボードを初期化中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-gray-900 p-4 md:p-6">
      <div className="mx-auto w-full max-w-[1600px]">
        {/* Header */}
        <div className="mb-6 flex items-center gap-3">
          <span className="text-2xl">📊</span>
          <h1 className="text-xl font-bold text-white">売上予測ダッシュボード</h1>
        </div>

        {/* Controls */}
        <div className="mb-6 rounded-xl border border-gray-700 bg-gray-800/50 p-4">
          <div className="flex flex-wrap items-end gap-4">
            {/* Store Type Selector */}
            <div className="min-w-[180px] flex-1">
              <label className="mb-1.5 block text-sm text-gray-400">業態</label>
              <select
                value={selectedStoreType}
                onChange={(e) => setSelectedStoreType(e.target.value)}
                className="w-full rounded-lg border border-gray-600 bg-gray-700 px-3 py-2 text-sm text-white focus:border-purple-500 focus:outline-none"
              >
                {storeTypes.map((st) => (
                  <option key={st} value={st}>
                    {st}
                  </option>
                ))}
              </select>
            </div>

            {/* Start Date */}
            <div className="min-w-[160px] flex-1">
              <label className="mb-1.5 block text-sm text-gray-400">開始日</label>
              <input
                type="date"
                value={startDate}
                min={minDate}
                max={maxDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full rounded-lg border border-gray-600 bg-gray-700 px-3 py-2 text-sm text-white focus:border-purple-500 focus:outline-none"
              />
            </div>

            {/* End Date */}
            <div className="min-w-[160px] flex-1">
              <label className="mb-1.5 block text-sm text-gray-400">終了日</label>
              <input
                type="date"
                value={endDate}
                min={minDate}
                max={maxDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full rounded-lg border border-gray-600 bg-gray-700 px-3 py-2 text-sm text-white focus:border-purple-500 focus:outline-none"
              />
            </div>

            {/* Buttons */}
            <div className="flex gap-2">
              <button
                onClick={fetchData}
                disabled={loading.data}
                className="rounded-lg bg-purple-600 px-6 py-2 text-sm font-medium text-white transition-colors hover:bg-purple-500 disabled:opacity-50"
              >
                {loading.data ? '読込中...' : '更新'}
              </button>
              <button
                onClick={handleExportPdf}
                disabled={exporting || loading.data}
                className="rounded-lg border border-gray-600 bg-gray-700 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-600 hover:text-white disabled:opacity-50"
                title="チャートと分析結果をPDFでダウンロード"
              >
                {exporting ? '出力中...' : '📄 レポート出力'}
              </button>
            </div>
          </div>
        </div>

        {/* Error display */}
        {error && (
          <div className="mb-4 rounded-xl border border-red-700 bg-red-900/20 p-3">
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {/* Chart (with ref for PDF) */}
        <div className="mb-6" ref={chartRef}>
          <ForecastChart
            data={forecastData}
            loading={loading.data}
            error={null}
            onPointClick={handleAnalyzeError}
          />
        </div>

        {/* Analysis progress */}
        {analysisProgress && (
          <div className="mb-4 rounded-xl border border-blue-700/30 bg-blue-900/10 p-3">
            <p className="text-sm text-blue-300">{analysisProgress}</p>
          </div>
        )}

        {/* Explainability Panel (with ref for PDF) */}
        <div className="mb-6" ref={analysisRef}>
          <ExplainabilityPanel
            analysis={analysis}
            loading={loading.analysis}
            error={null}
            progressMessage={analysisProgress}
          />
        </div>

        {/* Footer */}
        <p className="mt-4 text-center text-xs text-gray-500">
          予測は DataRobot AutoTS モデルにより生成されています。チャート上のデータポイントをクリックすると AI 分析を実行できます。
        </p>
      </div>
    </div>
  );
};

export default ForecastDashboard;
