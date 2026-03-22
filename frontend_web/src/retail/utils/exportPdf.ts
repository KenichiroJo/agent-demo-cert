/**
 * PDF エクスポートユーティリティ
 * ダッシュボードのチャート + 分析結果を A4 横向き PDF に出力
 */

import html2canvas from 'html2canvas';
import { jsPDF } from 'jspdf';

interface ExportOptions {
  storeType: string;
  startDate: string;
  endDate: string;
}

export async function exportDashboardPdf(
  chartRef: HTMLElement | null,
  analysisRef: HTMLElement | null,
  options: ExportOptions
): Promise<void> {
  if (!chartRef) {
    alert('チャートが表示されていません。');
    return;
  }

  const pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
  const pageW = pdf.internal.pageSize.getWidth();
  const pageH = pdf.internal.pageSize.getHeight();
  const margin = 10;
  const contentW = pageW - margin * 2;
  let yPos = margin;

  // --- Header ---
  pdf.setFontSize(16);
  pdf.setTextColor(60, 60, 60);
  pdf.text('Sales Forecast Report', margin, yPos + 6);
  yPos += 10;

  pdf.setFontSize(9);
  pdf.setTextColor(120, 120, 120);
  const now = new Date().toLocaleString('ja-JP');
  pdf.text(
    `Store: ${options.storeType}  |  Period: ${options.startDate} - ${options.endDate}  |  Generated: ${now}`,
    margin,
    yPos + 4
  );
  yPos += 10;

  // --- Divider ---
  pdf.setDrawColor(200, 200, 200);
  pdf.line(margin, yPos, pageW - margin, yPos);
  yPos += 5;

  // --- Chart capture ---
  try {
    const chartCanvas = await html2canvas(chartRef, {
      scale: 2,
      backgroundColor: '#1f2937',
      useCORS: true,
      logging: false,
    });
    const chartImg = chartCanvas.toDataURL('image/png');
    const chartAspect = chartCanvas.width / chartCanvas.height;
    const chartImgW = contentW;
    const chartImgH = contentW / chartAspect;

    const availableH = pageH - yPos - margin;
    const finalH = Math.min(chartImgH, availableH - 5);
    const finalW = finalH * chartAspect;

    pdf.addImage(chartImg, 'PNG', margin, yPos, Math.min(finalW, contentW), finalH);
    yPos += finalH + 5;
  } catch (e) {
    console.error('[PDF] Chart capture error:', e);
    pdf.setFontSize(10);
    pdf.setTextColor(200, 50, 50);
    pdf.text('Chart capture failed', margin, yPos + 5);
    yPos += 10;
  }

  // --- Analysis panel capture (if available) ---
  if (analysisRef && analysisRef.textContent && analysisRef.textContent.trim().length > 10) {
    // New page for analysis
    pdf.addPage();
    yPos = margin;

    pdf.setFontSize(14);
    pdf.setTextColor(60, 60, 60);
    pdf.text('AI Error Analysis Report', margin, yPos + 6);
    yPos += 12;

    try {
      const analysisCanvas = await html2canvas(analysisRef, {
        scale: 2,
        backgroundColor: '#1f2937',
        useCORS: true,
        logging: false,
      });
      const analysisImg = analysisCanvas.toDataURL('image/png');
      const analysisAspect = analysisCanvas.width / analysisCanvas.height;
      const analysisImgW = contentW;
      const analysisImgH = contentW / analysisAspect;

      const availH = pageH - yPos - margin;
      const finalH = Math.min(analysisImgH, availH);
      const finalW = finalH * analysisAspect;

      pdf.addImage(analysisImg, 'PNG', margin, yPos, Math.min(finalW, contentW), finalH);
    } catch (e) {
      console.error('[PDF] Analysis capture error:', e);
    }
  }

  // --- Footer on all pages ---
  const totalPages = pdf.getNumberOfPages();
  for (let i = 1; i <= totalPages; i++) {
    pdf.setPage(i);
    pdf.setFontSize(7);
    pdf.setTextColor(150, 150, 150);
    pdf.text(
      `Powered by DataRobot AutoTS + LLM Gateway  |  Page ${i}/${totalPages}`,
      margin,
      pageH - 5
    );
  }

  // --- Download ---
  const filename = `forecast_report_${options.storeType}_${options.startDate}_${options.endDate}.pdf`;
  pdf.save(filename);
}
