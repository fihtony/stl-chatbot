/**
 * Unified backend API client
 * For managing frontend-backend API communication
 *
 * Note: Admin API calls go through Next.js API routes at /api/admin/*
 * which proxy to the backend server. Non-admin calls may go directly to backend.
 */

// API base URL - for direct backend calls (non-admin APIs)
const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8086';

// API route prefix
const API_ADMIN_PREFIX = '/api/admin';

// ============== Type Definitions ==============

export interface ContentStatus {
  total_trunked_files: number;
  total_invalid_files: number;
  total_pdfs: number;
  valid_trunked_files: { name: string; size: number; path: string }[];
  invalid_files: { name: string; size: number; path: string; reason: string }[];
  pdf_files: { name: string; size: number; path: string }[];
  scraped_dir: string;
  analyzed_at: string;
}

export interface ScrapeStatus {
  is_running: boolean;
  start_time: number | null;
  current_page: string;
  total_pages: number;
  new_pages: number;
  downloaded_pdfs: number;
  new_documents: number;
  total_pdfs: number;
  last_run: string | null;
  error_message: string;
}

export interface ScrapeConfig {
  school_url: string;
  schedule_enabled: boolean;
  schedule_time: string;  // HH:MM format
  output_dir: string;
  timeout: number;
  respect_robots_txt: boolean;
}

export interface AIInfo {
  provider: string;
  base_url: string;
  model: string;
  embedding_model: string;
  embedding_device: string;
}

export interface AITestResult {
  provider: string;
  model: string;
  response: string;
  latency_ms: number;
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export interface UploadStatus {
  counts: {
    pdfTexts: number;
    pages: number;
    external: number;
  };
  total: number;
  status: string;
}

// ============== API Client Class ==============

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  /**
   * Unified request handling method
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const url = `${this.baseUrl}${endpoint}`;

    const defaultHeaders = {
      'Content-Type': 'application/json',
    };

    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          ...defaultHeaders,
          ...options.headers,
        },
      });

      const data = await response.json();

      if (!response.ok) {
        return {
          success: false,
          error: data.error || `HTTP ${response.status}: ${response.statusText}`,
        };
      }

      // Handle both wrapped responses (with `data` property) and direct responses
      // Direct response: {status: "ok", chunks: 409, ...}
      // Wrapped response: {success: true, data: {...}}
      const responseData = data.data !== undefined ? data.data : data;

      return {
        success: data.success ?? true,
        data: responseData as T,
        error: data.error,
        message: data.message,
      };
    } catch (error) {
      // Network error or other error
      const errorMessage = error instanceof Error
        ? error.message
        : String(error);

      console.error(`API request failed [${endpoint}]:`, errorMessage);

      return {
        success: false,
        error: `Network error: ${errorMessage}`,
      };
    }
  }

  // ============== Content Management API ==============

  /**
   * Get content status
   * Note: Uses Next.js API route proxy at /api/admin/content-status
   */
  async getContentStatus(): Promise<ApiResponse<ContentStatus>> {
    // Use relative URL to go through Next.js API proxy
    const url = `${API_ADMIN_PREFIX}/content-status`;
    const response = await fetch(url);
    const data = await response.json();

    if (!response.ok) {
      return {
        success: false,
        error: data.error || `HTTP ${response.status}`,
      };
    }

    return {
      success: data.success ?? true,
      data: data.data,
      error: data.error,
      message: data.message,
    };
  }

  // ============== Crawler Management API ==============

  /**
   * Get crawler status
   * Note: Uses Next.js API route proxy at /api/admin/scrape-status
   */
  async getScrapeStatus(): Promise<ApiResponse<ScrapeStatus>> {
    const url = `${API_ADMIN_PREFIX}/scrape-status`;
    const response = await fetch(url);
    const data = await response.json();

    if (!response.ok) {
      return { success: false, error: data.error || `HTTP ${response.status}` };
    }

    return {
      success: data.success ?? true,
      data: data.data,
      error: data.error,
      message: data.message,
    };
  }

  /**
   * Refresh crawler status (alias for getScrapeStatus)
   * Provided for semantic clarity in component usage
   */
  async refreshScrapeStatus(): Promise<ApiResponse<ScrapeStatus>> {
    return this.getScrapeStatus();
  }

  /**
   * Get crawler configuration
   * Note: Uses Next.js API route proxy at /api/admin/scrape-config
   */
  async getScrapeConfig(): Promise<ApiResponse<ScrapeConfig>> {
    const url = `${API_ADMIN_PREFIX}/scrape-config`;
    const response = await fetch(url);
    const data = await response.json();

    if (!response.ok) {
      return { success: false, error: data.error || `HTTP ${response.status}` };
    }

    return {
      success: data.success ?? true,
      data: data.data,
      error: data.error,
      message: data.message,
    };
  }

  /**
   * Save crawler configuration
   * Note: Uses Next.js API route proxy at /api/admin/scrape-config
   */
  async saveScrapeConfig(config: Partial<ScrapeConfig>): Promise<ApiResponse<ScrapeConfig>> {
    const url = `${API_ADMIN_PREFIX}/scrape-config`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    const data = await response.json();

    if (!response.ok) {
      return { success: false, error: data.error || `HTTP ${response.status}` };
    }

    return {
      success: data.success ?? true,
      data: data.data,
      error: data.error,
      message: data.message,
    };
  }

  /**
   * Trigger scraping
   * Note: Uses Next.js API route proxy at /api/admin/scrape-trigger
   */
  async triggerScrape(): Promise<ApiResponse<{ message: string }>> {
    const url = `${API_ADMIN_PREFIX}/scrape-trigger`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    const data = await response.json();

    if (!response.ok) {
      return { success: false, error: data.error || `HTTP ${response.status}` };
    }

    return {
      success: data.success ?? true,
      data: data.data,
      error: data.error,
      message: data.message,
    };
  }

  /**
   * Stop scraping
   * Note: Uses Next.js API route proxy at /api/admin/scrape-stop
   */
  async stopScrape(): Promise<ApiResponse<{ message: string }>> {
    const url = `${API_ADMIN_PREFIX}/scrape-stop`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    const data = await response.json();

    if (!response.ok) {
      return { success: false, error: data.error || `HTTP ${response.status}` };
    }

    return {
      success: data.success ?? true,
      data: data.data,
      error: data.error,
      message: data.message,
    };
  }

  /**
   * Get scheduler status
   * Note: Uses Next.js API route proxy at /api/admin/scheduler-status
   */
  async getSchedulerStatus(): Promise<ApiResponse<{
    enabled: boolean;
    schedule_time: string;
    running: boolean;
    next_run: string;
    jobs: number;
    last_run_status: 'completed' | 'error' | null;
    last_run_time: string | null;
  }>> {
    const url = `${API_ADMIN_PREFIX}/scheduler-status`;
    const response = await fetch(url);
    const data = await response.json();

    if (!response.ok) {
      return { success: false, error: data.error || `HTTP ${response.status}` };
    }

    return {
      success: data.success ?? true,
      data: data.data,
      error: data.error,
      message: data.message,
    };
  }

  // ============== AI Management API ==============

  /**
   * Get AI configuration information
   * Note: Uses Next.js API route proxy at /api/admin/ai-info
   */
  async getAIInfo(): Promise<ApiResponse<AIInfo>> {
    const url = `${API_ADMIN_PREFIX}/ai-info`;
    const response = await fetch(url);
    const data = await response.json();

    if (!response.ok) {
      return { success: false, error: data.error || `HTTP ${response.status}` };
    }

    return {
      success: data.success ?? true,
      data: data.data,
      error: data.error,
      message: data.message,
    };
  }

  /**
   * Test AI connection
   * Note: Uses Next.js API route proxy at /api/admin/ai-test
   */
  async testAIConnection(testMessage: string = 'Hello, please respond with "Connection successful"'): Promise<ApiResponse<AITestResult>> {
    const url = `${API_ADMIN_PREFIX}/ai-test`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ test_message: testMessage }),
    });
    const data = await response.json();

    if (!response.ok) {
      return { success: false, error: data.error || `HTTP ${response.status}` };
    }

    return {
      success: data.success ?? true,
      data: data.data,
      error: data.error,
      message: data.message,
    };
  }

  // ============== File Upload API (Local Next.js API routes) ==============

  /**
   * Get upload status
   */
  async getUploadStatus(): Promise<{ status: string; counts: { pdfTexts: number; pages: number; external: number }; total: number }> {
    const response = await fetch('/api/upload-data');
    return response.json();
  }

  /**
   * Upload files
   */
  async uploadFiles(files: File[]): Promise<ApiResponse<{ message: string; total: number }>> {
    const formData = new FormData();

    for (const file of files) {
      const fileName = file.name.toLowerCase();
      let folder = 'pages';

      if (fileName.includes('pdf') && (fileName.endsWith('.txt') || fileName.match(/_[a-f0-9]+\.txt$/))) {
        folder = 'pdf-texts';
      } else if (fileName.includes('external') || fileName.includes('wp-content') || fileName.includes('http')) {
        folder = 'external';
      }

      formData.append(`${folder}/${file.name}`, file);
    }

    try {
      const response = await fetch('/api/upload-data', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (response.ok && data.success) {
        return {
          success: true,
          data: {
            message: data.message,
            total: data.total,
          },
        };
      }

      return {
        success: false,
        error: data.error || data.message || 'Upload failed',
      };
    } catch (error) {
      const errorMessage = error instanceof Error
        ? error.message
        : String(error);

      console.error('File upload failed:', errorMessage);

      return {
        success: false,
        error: `Upload error: ${errorMessage}`,
      };
    }
  }

  // ============== Database Management API ==============

  /**
   * Get database statistics
   */
  async getDbStats(): Promise<ApiResponse<{
    documents: number;
    chunks: number;
    index_type: string;
    embedding_model: string;
  }>> {
    return this.request(`${API_ADMIN_PREFIX}/db-stats`);
  }

  /**
   * Clear database
   */
  async clearDatabase(): Promise<ApiResponse<{ message: string; deleted_count: number }>> {
    return this.request(`${API_ADMIN_PREFIX}/clear-database`, {
      method: 'POST',
    });
  }

  /**
   * Execute data migration
   */
  async migrateData(): Promise<ApiResponse<{ message: string; migrated_count: number }>> {
    return this.request(`${API_ADMIN_PREFIX}/migrate`, {
      method: 'POST',
    });
  }

  /**
   * Execute deduplication
   */
  async deduplicate(): Promise<ApiResponse<{ message: string; original_count: number; deduplicated_count: number }>> {
    return this.request(`${API_ADMIN_PREFIX}/deduplicate`, {
      method: 'POST',
    });
  }

  // ============== Incremental Indexing API ==============

  /**
   * Index specific uploaded files
   * Note: Uses Next.js API route proxy at /api/admin/index-files
   */
  async indexFiles(files: string[]): Promise<ApiResponse<{
    message: string;
    chunks_indexed: number;
    files_processed: number;
  }>> {
    const url = `${API_ADMIN_PREFIX}/index-progress`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ files }),
    });
    const data = await response.json();

    if (!response.ok) {
      return { success: false, error: data.error || `HTTP ${response.status}` };
    }

    return {
      success: data.success ?? true,
      data: data.data,
      error: data.error,
      message: data.message,
    };
  }

  /**
   * Automatically find and index new files
   * Note: Uses Next.js API route proxy at /api/admin/index-new
   */
  async indexNewFiles(): Promise<ApiResponse<{
    message: string;
    chunks_indexed: number;
    files_processed: number;
  }>> {
    const url = `${API_ADMIN_PREFIX}/index-new`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    const data = await response.json();

    if (!response.ok) {
      return { success: false, error: data.error || `HTTP ${response.status}` };
    }

    return {
      success: data.success ?? true,
      data: data.data,
      error: data.error,
      message: data.message,
    };
  }

  /**
   * Get current indexing progress
   * Note: Uses Next.js API route proxy at /api/admin/index-progress
   */
  async getIndexProgress(): Promise<ApiResponse<{
    status: string;
    current_file: string;
    total_chunks: number;
    processed_chunks: number;
    files_to_process: number;
    processed_files: number;
    progress_percent: number;
    error_message: string;
  }>> {
    const url = `${API_ADMIN_PREFIX}/index-progress`;
    const response = await fetch(url);
    const data = await response.json();

    if (!response.ok) {
      return { success: false, error: data.error || `HTTP ${response.status}` };
    }

    return {
      success: data.success ?? true,
      data: data,
      error: data.error,
      message: data.message,
    };
  }

  /**
   * Reset index progress tracker
   * Note: Uses Next.js API route proxy at /api/admin/index-reset
   */
  async resetIndexProgress(): Promise<ApiResponse<{ message: string }>> {
    const url = `${API_ADMIN_PREFIX}/index-new`;
    const response = await fetch(url, {
      method: 'DELETE',
    });
    const data = await response.json();

    if (!response.ok) {
      return { success: false, error: data.error || `HTTP ${response.status}` };
    }

    return {
      success: data.success ?? true,
      data: data,
      error: data.error,
      message: data.message,
    };
  }

  // ============== Performance Metrics API ==============

  /**
   * Get performance metrics
   * Note: Uses Next.js API route proxy at /api/admin/performance-metrics
   */
  async getPerformanceMetrics(): Promise<ApiResponse<{
    status: string;
    summary: {
      total_queries: number;
      avg_response_time_ms: number;
      p50_ms: number;
      p95_ms: number;
      p99_ms: number;
    };
    by_language: Record<string, { count: number; avg_ms: number; total_ms: number }>;
    by_path: Record<string, { count: number; avg_ms: number; total_ms: number }>;
    stages: Record<string, any>;
  }>> {
    const url = `${API_ADMIN_PREFIX}/performance-metrics`;
    const response = await fetch(url);
    const data = await response.json();

    if (!response.ok) {
      return { success: false, error: data.error || `HTTP ${response.status}` };
    }

    return {
      success: data.success ?? true,
      data: data,
      error: data.error,
      message: data.message,
    };
  }
}

// ============== Export Singleton ==============

// Export default API client instance
export const api = new ApiClient();

// Export factory function, allows creating clients with custom configuration
export const createApiClient = (baseUrl?: string): ApiClient => {
  return new ApiClient(baseUrl);
};

// Export types for external use
export type {
  ApiClient as ApiClientClass
};
