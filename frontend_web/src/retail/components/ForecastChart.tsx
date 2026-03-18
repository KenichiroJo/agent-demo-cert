/**
 * 予測 vs 実績 チャートコンポーネント (ERCOT スタイル)
 * - 信頼区間バンド (グレー背景)
 * - 誤差比例ドットサイズ (大きい誤差 = 大きいドット + 色変化)
 * - ワンクリックで即座に誤差分析起動
 */

import React, { useMemo, useCallback, useRef } from 'react';
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
  errorHigh: '#EF4444',
  errorMed: '#F59E0B',
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
  const analysisTriggeredRef = useRef(false);

  // 誤差の統計を計算 (ドットサイズスケーリング用)
  const errorStats = useMemo(() => {
    const absErrors = data
      .map((d) => Math.abs(d.pct_error || 0))
      .filter((e) => e > 0);
    if (absErrors.length === 0) return { max: 1, p75: 1, p50: 1 };
    const sorted = [...absErrors].sort((a, b) => a - b);
    return {
      max: sorted[sorted.length - 1],
      p75: sorted[Math.floor(sorted.length * 0.75)] || 1,
      p50: sorted[Math.floor(sorted.length * 0.5)] || 1,
    };
  }, [data]);

  const chartData = useMemo(() => {
    return data.map((point) => ({
      ...point,
      displayDate: new Date(point.date).toLocaleDateString('ja-JP', {
        year: 'numeric',
        month: 'short',
      }),
      fullDate: point.date,
      absPctError: Math.abs(point.pct_error || 0),
    }));
  }, [data]);

  const stats = useMemo(() => {
    if (data.length === 0) return null;
    const withPred = data.filter((d) => d.predicted_sales != null && d.actual_sales != null);
    const errors = withPred.map((d) => d.error || 0).filter((e) => e !== 0);
    if (errors.length === 0) return null;
    const rmse = Math.sqrt(errors.reduce((sum, e) => sum + e * e, 0) / errors.length);
    const mae = errors.reduce((sum, e) => sum + Math.abs(e), 0) / errors.length;
    const pctErrors = withPred.map((d) => Math.abs(d.pct_error || 0)).filter((e) => e > 0);
    const mape = pctErrors.length > 0 ? pctErrors.reduce((sum, e) => sum + e, 0) / pctErrors.length : 0;
    const maxErr = Math.max(...errors.map(Math.abs));
    return {
      rmse: rmse.toFixed(2),
      mae: mae.toFixed(2),
      mape: mape.toFixed(1),
      maxError: maxErr.toFixed(2),
      count: errors.length,
    };
  }, [data]);

  // ワンクリック: チャートクリック → 即座に onPointClick を呼び出して分析開始
  const triggerAnalysis = useCallback(
    (point: ForecastData) => {
      console.log('[ForecastChart] triggerAnalysis called:', {
        store_type: point.store_type,
        date: point.date,
        predicted_sales: point.predicted_sales,
        hasOnPointClick: !!onPointClick,
      });

      if (onPointClick && point.predicted_sales != null) {
        // 重複トリガー防止
        if (analysisTriggeredRef.current) {
          console.log('[ForecastChart] Analysis already triggered, skipping');
          return;
        }
        analysisTriggeredRef.current = true;
        setTimeout(() => { analysisTriggeredRef.current = false; }, 2000);

        console.log('[ForecastChart] Calling onPointClick...');
        onPointClick(point);
      } else {
        console.log('[ForecastChart] Skipped: onPointClick=', !!onPointClick, 'predicted_sales=', point.predicted_sales);
      }
    },
    [onPointClick]
  );

  // ERCOTスタイル: 誤差の大きさに応じたドットサイズ・色を返すカスタムドット
  const CustomActualDot = useCallback(
    (props: any) => {
      const { cx, cy, payload } = props;
      if (cx == null || cy == null) return null;

      const absPct = Math.abs(payload?.pct_error || 0);
      const hasPrediction = payload?.predicted_sales != null;

      // 予測がない期間はデフォルト小ドット
      if (!hasPrediction) {
        return <circle cx={cx} cy={cy} r={3} fill={CHART_COLORS.actual} stroke="none" />;
      }

      // 誤差レベルに応じたサイズ・色
      let radius = 3;
      let color = CHART_COLORS.actual;

      if (absPct > errorStats.p75) {
        radius = 7;
        color = CHART_COLORS.errorHigh; // 赤
      } else if (absPct > errorStats.p50) {
        radius = 5;
        color = CHART_COLORS.errorMed; // 黄
      }

      return (
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          fill={color}
          stroke="#fff"
          strokeWidth={radius > 3 ? 1.5 : 0}
          style={{ cursor: 'pointer' }}
        />
      );
    },
    [errorStats]
  );

  // activeDot クリックハンドラ (Recharts が activeDot の onClick に渡す引数)
  const handleActiveDotClick = useCallback(
    (dotData: any, _index: number, e: React.MouseEvent) => {
      e?.stopPropagation?.();
      const point = dotData?.payload || dotData;
      console.log('[ForecastChart] activeDot clicked:', point?.date, point?.store_type);
      if (point) {
        triggerAnalysis(point as ForecastData);
      }
    },
    [triggerAnalysis]
  );

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      const d = payload[0].payload;
      const hasPred = d.predicted_sales != null;
      return (
        <div className="pointer-events-none rounded-lg border border-gray-600 bg-gray-800 p-3 text-sm shadow-lg">
          <p className="mb-2 font-medium text-white">{label}</p>
          <div className="flex flex-col gap-1">
            {d.actual_sales != null && (
              <p className="text-orange-400">実績: {d.actual_sales.toFixed(2)} 億円</p>
            )}
            {hasPred && (
              <p className="text-purple-400">予測: {d.predicted_sales.toFixed(2)} 億円</p>
            )}
            {hasPred && d.error != null && (
              <p className={Math.abs(d.pct_error || 0) > 5 ? 'text-red-400' : 'text-gray-400'}>
                誤差: {Math.abs(d.error).toFixed(2)} 億円 ({Math.abs(d.pct_error || 0).toFixed(1)}%)
              </p>
            )}
            {hasPred && (
              <p className="mt-1 text-xs text-gray-500">
                クリックで即座に AI 分析開始
              </p>
            )}
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
            <span
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                parseFloat(stats.rmse) > 0.5
                  ? 'bg-red-900/50 text-red-300'
                  : 'bg-green-900/50 text-green-300'
              }`}
            >
              RMSE: {stats.rmse}
            </span>
            <span className="rounded-full bg-gray-700 px-3 py-1 text-xs font-medium text-gray-300">
              MAE: {stats.mae}
            </span>
            <span className="rounded-full bg-gray-700 px-3 py-1 text-xs font-medium text-gray-300">
              MAPE: {stats.mape}%
            </span>
            <span className="rounded-full bg-gray-700 px-3 py-1 text-xs font-medium text-gray-300">
              最大誤差: {stats.maxError}億円
            </span>
          </div>
        )}
      </div>

      <div>
        <ResponsiveContainer width="100%" height={420}>
          <ComposedChart
            data={chartData}
            margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
            onClick={(chartState: any) => {
              console.log('[ForecastChart] ComposedChart onClick fired', chartState?.activePayload?.length);
              if (chartState?.activePayload?.length > 0) {
                const pt = chartState.activePayload[0].payload as ForecastData;
                triggerAnalysis(pt);
              }
            }}
            style={{ cursor: 'crosshair' }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
            <XAxis
              dataKey="displayDate"
              tick={{ fontSize: 11, fill: CHART_COLORS.text }}
              angle={-45}
              textAnchor="end"
              height={60}
              stroke={CHART_COLORS.grid}
            />
            <YAxis
              label={{
                value: '売上高（億円）',
                angle: -90,
                position: 'insideLeft',
                style: { fill: CHART_COLORS.text, fontSize: 12 },
              }}
              tick={{ fontSize: 11, fill: CHART_COLORS.text }}
              stroke={CHART_COLORS.grid}
            />
            <Tooltip
              content={<CustomTooltip />}
              cursor={{ stroke: CHART_COLORS.predicted, strokeWidth: 1, strokeDasharray: '5 5' }}
            />
            <Legend wrapperStyle={{ paddingTop: '20px', fontSize: '12px' }} iconType="line" />

            {/* 信頼区間バンド (灰色背景) */}
            <Area
              type="monotone"
              dataKey="confidence_high"
              stroke="none"
              fill={CHART_COLORS.confidence}
              fillOpacity={0.15}
              name="90%信頼区間(上限)"
              isAnimationActive={false}
              connectNulls={false}
            />
            <Area
              type="monotone"
              dataKey="confidence_low"
              stroke="none"
              fill="#1F2937"
              fillOpacity={0.8}
              name="90%信頼区間(下限)"
              isAnimationActive={false}
              connectNulls={false}
            />

            {/* 予測線 (紫・点線) */}
            <Line
              type="monotone"
              dataKey="predicted_sales"
              stroke={CHART_COLORS.predicted}
              strokeWidth={2}
              name="予測売上"
              strokeDasharray="5 5"
              dot={{ r: 2, fill: CHART_COLORS.predicted }}
              activeDot={{
                r: 5,
                fill: CHART_COLORS.predicted,
                stroke: '#fff',
                strokeWidth: 2,
                cursor: 'pointer',
                onClick: handleActiveDotClick,
              }}
              isAnimationActive={false}
              connectNulls={false}
            />

            {/* 実績線 (オレンジ・誤差比例ドット) */}
            <Line
              type="monotone"
              dataKey="actual_sales"
              stroke={CHART_COLORS.actual}
              strokeWidth={2}
              name="実績売上"
              dot={<CustomActualDot />}
              activeDot={{
                r: 8,
                fill: CHART_COLORS.actual,
                stroke: '#fff',
                strokeWidth: 2,
                cursor: 'pointer',
                onClick: handleActiveDotClick,
              }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* ヒントテキスト */}
      <div className="mt-3 rounded-lg border border-blue-800/30 bg-blue-900/10 p-3">
        <p className="text-sm text-blue-300">
          💡 予測データがある区間のデータポイントをクリックすると、AI による予測誤差の{' '}
          <strong>根本原因分析</strong>が即座に開始されます。
        </p>
      </div>
    </div>
  );
};

export default ForecastChart;
