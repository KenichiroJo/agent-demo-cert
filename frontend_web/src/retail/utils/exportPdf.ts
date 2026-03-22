/**
 * PDF エクスポートユーティリティ
 * ダッシュボードのチャート + 分析結果を A4 横向き PDF に出力
 *
 * Recharts の SVG チャートは html2canvas で直接キャプチャできないため、
 * SVG → Canvas 変換を先に行い、その後 html2canvas でキャプチャする。
 */

import html2canvas from 'html2canvas';
import { jsPDF } from 'jspdf';

interface ExportOptions {
  storeType: string;
  startDate: string;
  endDate: string;
}

/**
 * SVG 要素を inline style に変換して html2canvas でキャプチャできるようにする
 */
function inlineSvgStyles(element: HTMLElement): void {
  const svgs = element.querySelectorAll('svg');
  svgs.forEach((svg) => {
    // SVG に明示的な width/height を設定
    const bbox = svg.getBoundingClientRect();
    svg.setAttribute('width', String(bbox.width));
    svg.setAttribute('height', String(bbox.height));

    // 全子要素の computed style を inline に変換
    const allElements = svg.querySelectorAll('*');
    allElements.forEach((el) => {
      const computed = window.getComputedStyle(el);
      const important = [
        'fill', 'stroke', 'stroke-width', 'stroke-dasharray',
        'opacity', 'font-size', 'font-family', 'font-weight',
        'text-anchor', 'dominant-baseline', 'transform',
      ];
      important.forEach((prop) => {
        const val = computed.getPropertyValue(prop);
        if (val && val !== 'none' && val !== 'normal' && val !== '0') {
          (el as HTMLElement).style.setProperty(prop, val);
        }
      });
    });
  });
}

async function captureElement(element: HTMLElement): Promise<HTMLCanvasElement> {
  // Clone to avoid modifying the original DOM
  const clone = element.cloneNode(true) as HTMLElement;
  clone.style.position = 'absolute';
  clone.style.left = '-9999px';
  clone.style.top = '0';
  clone.style.width = `${element.offsetWidth}px`;
  document.body.appendChild(clone);

  try {
    inlineSvgStyles(clone);
    const canvas = await html2canvas(clone, {
      scale: 2,
      backgroundColor: '#1f2937',
      useCORS: true,
      logging: false,
      allowTaint: true,
      foreignObjectRendering: true,
    });
    return canvas;
  } finally {
    document.body.removeChild(clone);
  }
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

  // --- Chart capture (with SVG inline style fix) ---
  try {
    console.log('[PDF] Capturing chart...');
    const chartCanvas = await captureElement(chartRef);
    const chartImg = chartCanvas.toDataURL('image/png');
    const chartAspect = chartCanvas.width / chartCanvas.height;

    const availableH = pageH - yPos - margin - 5;
    const finalH = Math.min(contentW / chartAspect, availableH);
    const finalW = finalH * chartAspect;

    pdf.addImage(chartImg, 'PNG', margin, yPos, Math.min(finalW, contentW), finalH);
    yPos += finalH + 5;
    console.log('[PDF] Chart captured successfully');
  } catch (e) {
    console.error('[PDF] Chart capture error:', e);
    pdf.setFontSize(10);
    pdf.setTextColor(200, 50, 50);
    pdf.text('Chart capture failed: ' + String(e), margin, yPos + 5);
    yPos += 10;
  }

  // --- Analysis panel capture (if available) ---
  if (analysisRef && analysisRef.textContent && analysisRef.textContent.trim().length > 10) {
    pdf.addPage();
    yPos = margin;

    pdf.setFontSize(14);
    pdf.setTextColor(60, 60, 60);
    pdf.text('AI Error Analysis Report', margin, yPos + 6);
    yPos += 12;

    try {
      console.log('[PDF] Capturing analysis panel...');
      const analysisCanvas = await captureElement(analysisRef);
      const analysisImg = analysisCanvas.toDataURL('image/png');
      const analysisAspect = analysisCanvas.width / analysisCanvas.height;

      const availH = pageH - yPos - margin;
      const finalH = Math.min(contentW / analysisAspect, availH);
      const finalW = finalH * analysisAspect;

      pdf.addImage(analysisImg, 'PNG', margin, yPos, Math.min(finalW, contentW), finalH);
      console.log('[PDF] Analysis panel captured successfully');
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
  console.log(`[PDF] Saved: ${filename}`);
}
