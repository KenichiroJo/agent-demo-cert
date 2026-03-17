/**
 * API Service for Retail Forecast Analytics
 */

import axios, { type AxiosInstance, type AxiosError } from 'axios';
import { getApiUrl } from '@/lib/url-utils';

const API_BASE_URL = getApiUrl();

const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response) {
      console.error('Retail API Error:', error.response.data);
    }
    return Promise.reject(error);
  }
);

// Types
export interface ForecastData {
  date: string;
  store_type: string;
  actual_sales: number;
  predicted_sales: number | null;
  error: number | null;
  abs_error: number | null;
  pct_error: number | null;
  confidence_low: number | null;
  confidence_high: number | null;
}

export interface ErrorMetrics {
  store_type: string;
  rmse: number;
  mae: number;
  mape: number;
}

export interface ErrorAnalysisRequest {
  store_type: string;
  date: string;
}

export interface ErrorAnalysisResponse {
  store_type: string;
  date: string;
  actual_sales: number;
  predicted_sales: number;
  error: number;
  analysis: {
    summary: string;
    factors: Array<{
      factor: string;
      impact: string;
      detail: string;
      value?: number;
    }>;
    market_conditions: {
      description: string;
    };
    news_appendix?: string[];
    vdb_reports?: string[];
  };
  rmse_context?: {
    store_type_rmse?: number;
    store_type_mae?: number;
    overall_percentile?: number;
    z_score?: number;
  };
  hypothesis: string;
  confidence_score: number;
  supporting_evidence: Array<{
    factor: string;
    impact: string;
    detail: string;
    value?: number;
  }>;
  recommendations?: string[];
}

// API Methods
class RetailAPIService {
  async getStoreTypes(): Promise<string[]> {
    const response = await apiClient.get('/retail/api/store-types');
    const raw = typeof response.data === 'string' ? JSON.parse(response.data) : response.data;
    const types = raw?.store_types;
    return Array.isArray(types) ? types : [];
  }

  async getDateRange(): Promise<{ start_date: string; end_date: string }> {
    const response = await apiClient.get('/retail/api/date-range');
    const raw = typeof response.data === 'string' ? JSON.parse(response.data) : response.data;
    return {
      start_date: raw?.start_date || '',
      end_date: raw?.end_date || '',
    };
  }

  async getForecastData(params: {
    store_type: string;
    start_date?: string;
    end_date?: string;
  }): Promise<ForecastData[]> {
    const response = await apiClient.get('/retail/api/forecast-data', { params });
    const raw = typeof response.data === 'string' ? JSON.parse(response.data) : response.data;
    const data = raw?.data;
    return Array.isArray(data) ? data : [];
  }

  async getErrorMetrics(store_type: string): Promise<ErrorMetrics> {
    const response = await apiClient.get('/retail/api/error-metrics', {
      params: { store_type },
    });
    return response.data?.metrics;
  }

  async analyzeError(
    request: ErrorAnalysisRequest,
    onProgress?: (status: string, elapsed?: number) => void
  ): Promise<ErrorAnalysisResponse> {
    return new Promise((resolve, reject) => {
      const baseURL = API_BASE_URL.endsWith('/') ? API_BASE_URL : `${API_BASE_URL}/`;
      const url = new URL('retail/api/analyze-error', baseURL).toString();

      fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        credentials: 'include',
        body: JSON.stringify(request),
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }

          const reader = response.body?.getReader();
          const decoder = new TextDecoder();

          if (!reader) {
            reject(new Error('No response body'));
            return;
          }

          let buffer = '';

          const processStream = async () => {
            try {
              while (true) {
                const { done, value } = await reader.read();

                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const normalized = buffer.replace(/\r\n/g, '\n');
                const parts = normalized.split('\n\n');
                buffer = parts.pop() || '';

                for (const part of parts) {
                  if (!part.trim() || part.startsWith(':')) continue;

                  const lines = part.split('\n');
                  let eventName = '';
                  let eventData = '';

                  for (const line of lines) {
                    if (line.startsWith('event:')) {
                      eventName = line.substring(6).trim();
                    } else if (line.startsWith('data:')) {
                      eventData = line.substring(5).trim();
                    }
                  }

                  if (!eventName || !eventData) continue;

                  try {
                    const data = JSON.parse(eventData);

                    if (eventName === 'start') {
                      onProgress?.('started');
                    } else if (eventName === 'heartbeat') {
                      onProgress?.('processing', data.elapsed);
                    } else if (eventName === 'complete') {
                      resolve(data as ErrorAnalysisResponse);
                      return;
                    } else if (eventName === 'error') {
                      reject(new Error(data.error));
                      return;
                    }
                  } catch {
                    // skip unparseable
                  }
                }
              }
            } catch (error) {
              reject(error);
            }
          };

          processStream();
        })
        .catch((error) => {
          reject(error);
        });
    });
  }
}

export const retailApiService = new RetailAPIService();
export default retailApiService;
