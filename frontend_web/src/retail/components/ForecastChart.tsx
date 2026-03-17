/**
 * 予測 vs 実績 チャートコンポーネント
 * Recharts を使用したインタラクティブな折れ線グラフ
 */

import React, { useMemo, useState, useCallback } from 'react';
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Area,
  ComposedChart,
} from 'recharts';
import type { ForecastData } from '../services/api';

const CHART_COLORS = {
  actual: '#F97316',
  predicted: '#8B5CF6',
  confidence: '#6B7280',
  grid: '#374151',
  text: '#9CA3AF',
};

interface ForecastChartProps {
  data: ForecastData[];
  loading?: boolean;
  error?: string | null;
  onPointClick?: (point: ForecastData) => void;
}

const ForecastChart: React.FC<ForecastChartProps> = ({
  data,
  loading = false,
  error = null,
  onPointClick,
}) => {
  const [selectedPoint, setSelectedPoint] = useState<ForecastData | null>(null);

  const chartData = useMemo(() => {
    return data.map((point) => ({
      ...point,
      displayDate: new Date(point.date).toLocaleDateString('ja-JP', {
        year: 'numeric',
        month: 'short',
      }),
      fullDate: point.date,
      errorMagnitude: Math.abs(point.error || 0),
    }));
  }, [data]);

  const stats = useMemo(() => {
    if (data.length === 0) return null;
    const errors = data.map((d) => Math.abs(d.error || 0)).filter((e) => e > 0);
    if (errors.length === 0) return null;
    const rmse = Math.sqrt(errors.reduce((sum, e) => sum + e * e, 0) / errors.length);
    const mae = errors.reduce((sum, e) => sum + e, 0) / errors.length;
    const pctErrors = data.map((d) => Math.abs(d.pct_error || 0)).filter((e) => e > 0);
    const mape = pctErrors.length > 0 ? pctErrors.reduce((sum, e) => sum + e, 0) / pctErrors.length : 0;
    return { rmse: rmse.toFixed(1), mae: mae.toFixed(1), mape: mape.toFixed(1), count: errors.length };
  }, [data]);

  const handleChartClick = useCallback((chartState: any) => {
    if (chartState?.activePayload?.length > 0) {
      setSelectedPoint(chartState.activePayload[0].payload as ForecastData);
    }
  }, []);

  const handleAnalyze = useCallback(() => {
    if (selectedPoint && onPointClick) {
      onPointClick(selectedPoint);
      setSelectedPoint(null);
    }
  }, [selectedPoint, onPointClick]);

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      const d = payload[0].payload;
      return (
        <div className="rounded-lg border border-gray-600 bg-gray-800 p-3 text-sm shadow-lg">
          <p className="mb-2 font-medium text-white">{label}</p>
          <div className="flex flex-col gap-1">
            {d.actual_sales != null && <p className="text-orange-400">実績: {d.actual_sales.toFixed(1)} 億円</p>}
            {d.predicted_sales != null && <p className="text-purple-400">予測: {d.predicted_sales.toFixed(1)} 億円</p>}
            {d.error != null && (
              <p className={Math.abs(d.error) > 5 ? 'text-red-400' : 'text-gray-400'}>
                誤差: {d.error.toFixed(1)} 億円 ({d.pct_error?.toFixed(1)}%)
              </p>
            )}
            <p className="mt-1 text-xs text-blue-400">クリックで誤差分析を実行 →</p>
          </div>
        </div>
      );
    }
    return null;
  };

  if (loading) {
    return (
      <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-8">
        <div className="flex items-center justify-center gap-3">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-purple-500 border-t-transparent" />
          <span className="text-gray-400">データを読み込み中...</span>
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

  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-8 text-center">
        <p className="text-gray-400">選択した条件に該当する予測データがありません。</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-4 shadow-lg">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-white">予測 vs 実績 売上推移</h2>
        {stats && (
          <div className="flex flex-wrap gap-2">
            <span className={`rounded-full px-3 py-1 text-xs font-medium ${parseFloat(stats.rmse) > 10 ? 'bg-red-900/50 text-red-300' : 'bg-green-900/50 text-green-300'}`}>
              RMSE: {stats.rmse}
            </span>
            <span className="rounded-full bg-gray-700 px-3 py-1 text-xs font-medium text-gray-300">MAE: {stats.mae}</span>
            <span className="rounded-full bg-gray-700 px-3 py-1 text-xs font-medium text-gray-300">MAPE: {stats.mape}%</span>
          </div>
        )}
      </div>

      <div className="select-none">
        <ResponsiveContainer width="100%" height={400}>
          <ComposedChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }} onClick={handleChartClick} style={{ cursor: 'crosshair' }}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
            <XAxis dataKey="displayDate" tick={{ fontSize: 11, fill: CHART_COLORS.text }} angle={-45} textAnchor="end" height={60} stroke={CHART_COLORS.grid} />
            <YAxis
              label={{ value: '売上高（億円）', angle: -90, position: 'insideLeft', style: { fill: CHART_COLORS.text, fontSize: 12 } }}
              tick={{ fontSize: 11, fill: CHART_COLORS.text }}
              stroke={CHART_COLORS.grid}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ stroke: CHART_COLORS.actual, strokeWidth: 1, strokeDasharray: '5 5' }} />
            <Legend wrapperStyle={{ paddingTop: '20px', fontSize: '12px' }} iconType="line" />
            <Area type="monotone" dataKey="confidence_high" stroke="none" fill={CHART_COLORS.confidence} fillOpacity={0.1} name="90%信頼区間(上限)" isAnimationActive={false} />
            <Area type="monotone" dataKey="confidence_low" stroke="none" fill={CHART_COLORS.confidence} fillOpacity={0.1} name="90%信頼区間(下限)" isAnimationActive={false} />
            <Line type="monotone" dataKey="actual_sales" stroke={CHART_COLORS.actual} strokeWidth={2} name="実績売上" dot={{ r: 3, fill: CHART_COLORS.actual }} activeDot={{ r: 6, fill: CHART_COLORS.actual, stroke: '#fff', strokeWidth: 2 }} isAnimationActive={false} />
            <Line type="monotone" dataKey="predicted_sales" stroke={CHART_COLORS.predicted} strokeWidth={2} name="予測売上" strokeDasharray="5 5" dot={{ r: 3, fill: CHART_COLORS.predicted }} activeDot={{ r: 6, fill: CHART_COLORS.predicted, stroke: '#fff', strokeWidth: 2 }} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {selectedPoint && (
        <div className="mt-4 rounded-lg border border-purple-700/50 bg-purple-900/20 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-white">
                選択: {selectedPoint.store_type} — {new Date(selectedPoint.date).toLocaleDateString('ja-JP')}
              </p>
              <p className="text-sm text-gray-400">
                実績: {selectedPoint.actual_sales?.toFixed(1)}億円 / 予測: {selectedPoint.predicted_sales?.toFixed(1)}億円 / 誤差: {Math.abs(selectedPoint.error || 0).toFixed(1)}億円
              </p>
            </div>
            <button onClick={handleAnalyze} className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-purple-500">
              誤差分析を実行
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ForecastChart;
