/**
 * Word レポートエクスポート
 * バックエンドの /api/retail/export-report から .doc ファイルをダウンロード
 */

import { getApiUrl } from '@/lib/url-utils';

interface ExportOptions {
  storeType: string;
  startDate: string;
  endDate: string;
  analysis?: any;
}

export async function exportDashboardPdf(
  _chartRef: HTMLElement | null,
  _analysisRef: HTMLElement | null,
  options: ExportOptions
): Promise<void> {
  const baseURL = getApiUrl();
  const url = new URL(
    'retail/export-report',
    baseURL.endsWith('/') ? baseURL : `${baseURL}/`
  ).toString();

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      store_type: options.storeType,
      start_date: options.startDate,
      end_date: options.endDate,
      analysis: options.analysis || null,
    }),
  });

  if (!response.ok) {
    throw new Error(`Export failed: ${response.status} ${response.statusText}`);
  }

  // Blob としてダウンロード
  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = `forecast_report_${options.storeType}_${options.startDate}_${options.endDate}.doc`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(downloadUrl);

  console.log(`[Report] Downloaded: ${a.download}`);
}
