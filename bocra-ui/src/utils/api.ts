/**
 * BOCRA Frontend API Client with IP-based Session Management
 * Handles secure communication with the backend API
 */

import axios, { AxiosInstance, AxiosResponse, AxiosError, InternalAxiosRequestConfig } from 'axios';

export interface ApiError {
  message: string;
  code?: string;
  status: number;
  details?: any;
}

export interface SessionInfo {
  sessionToken: string;
  ipHash: string;
  expiresAt: string;
  isActive: boolean;
}

export interface UserInfo {
  ipHash: string;
  documentCount: number;
  storageUsedBytes: number;
  quotaLimitBytes: number;
  quotaUsedPercent: number;
  activeSessionsCount: number;
  firstSeen: string;
  lastSeen: string;
  settings: {
    language: string;
    dpi: number;
    psm: number;
    fastMode: boolean;
    skipTables: boolean;
  };
}

export interface RateLimitInfo {
  requestsRemaining: number;
  requestsLimit: number;
  resetTime: number;
  windowSeconds: number;
}

class ApiClient {
  private client: AxiosInstance;
  private sessionToken: string | null = null;
  private rateLimitInfo: RateLimitInfo | null = null;

  constructor(baseURL: string = process.env.REACT_APP_API_URL || 'http://localhost:8000/api') {
    // Initialize axios client
    this.client = axios.create({
      baseURL,
      timeout: 30000, // 30 seconds
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Load session token from localStorage
    this.loadSessionFromStorage();

    // Setup request interceptor
    this.client.interceptors.request.use(
      this.handleRequestInterceptor.bind(this),
      this.handleRequestError.bind(this)
    );

    // Setup response interceptor
    this.client.interceptors.response.use(
      this.handleResponseInterceptor.bind(this),
      this.handleResponseError.bind(this)
    );
  }

  private loadSessionFromStorage(): void {
    try {
      const storedSession = localStorage.getItem('bocra_session_token');
      if (storedSession) {
        this.sessionToken = storedSession;
      }
    } catch (error) {
      console.warn('Failed to load session from storage:', error);
    }
  }

  private saveSessionToStorage(token: string): void {
    try {
      localStorage.setItem('bocra_session_token', token);
      this.sessionToken = token;
    } catch (error) {
      console.warn('Failed to save session to storage:', error);
    }
  }

  private removeSessionFromStorage(): void {
    try {
      localStorage.removeItem('bocra_session_token');
      this.sessionToken = null;
    } catch (error) {
      console.warn('Failed to remove session from storage:', error);
    }
  }

  private handleRequestInterceptor(config: InternalAxiosRequestConfig): InternalAxiosRequestConfig {
    // Add session token to requests
    if (this.sessionToken) {
      config.headers.Authorization = `Bearer ${this.sessionToken}`;
    }

    // Add request ID for tracking
    config.headers['X-Request-ID'] = this.generateRequestId();

    // Add client fingerprint for additional security
    config.headers['X-Client-Fingerprint'] = this.generateClientFingerprint();

    return config;
  }

  private handleRequestError(error: any): Promise<any> {
    return Promise.reject(this.transformError(error));
  }

  private handleResponseInterceptor(response: AxiosResponse): AxiosResponse {
    // Extract rate limit information from headers
    this.updateRateLimitInfo(response.headers);

    // Handle session token updates
    const newToken = response.headers['x-session-token'];
    if (newToken && newToken !== this.sessionToken) {
      this.saveSessionToStorage(newToken);
    }

    return response;
  }

  private handleResponseError(error: AxiosError): Promise<ApiError> {
    const apiError = this.transformError(error);

    // Handle authentication errors
    if (apiError.status === 401) {
      this.removeSessionFromStorage();
      // Optionally redirect to login or refresh the page
      window.dispatchEvent(new CustomEvent('bocra:auth-error', { detail: apiError }));
    }

    // Handle rate limiting
    if (apiError.status === 429) {
      this.updateRateLimitInfo(error.response?.headers || {});
      window.dispatchEvent(new CustomEvent('bocra:rate-limited', { detail: this.rateLimitInfo }));
    }

    return Promise.reject(apiError);
  }

  private transformError(error: AxiosError | any): ApiError {
    if (axios.isAxiosError(error)) {
      return {
        message: error.response?.data?.detail || error.message || 'Network error occurred',
        code: error.response?.data?.code || error.code,
        status: error.response?.status || 0,
        details: error.response?.data?.details,
      };
    }

    return {
      message: error.message || 'Unknown error occurred',
      status: 0,
    };
  }

  private updateRateLimitInfo(headers: any): void {
    const limit = headers['x-ratelimit-limit'];
    const remaining = headers['x-ratelimit-remaining'];
    const reset = headers['x-ratelimit-reset'];
    const window = headers['x-ratelimit-window'];

    if (limit && remaining && reset) {
      this.rateLimitInfo = {
        requestsLimit: parseInt(limit, 10),
        requestsRemaining: parseInt(remaining, 10),
        resetTime: parseInt(reset, 10),
        windowSeconds: window ? parseInt(window, 10) : 3600,
      };
    }
  }

  private generateRequestId(): string {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  private generateClientFingerprint(): string {
    // Generate a simple client fingerprint for additional security
    const userAgent = navigator.userAgent;
    const screenInfo = `${window.screen.width}x${window.screen.height}`;
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const language = navigator.language;
    
    const fingerprint = `${userAgent}-${screenInfo}-${timezone}-${language}`;
    return btoa(fingerprint).substr(0, 16);
  }

  // Public API methods

  /**
   * Initialize session (called automatically on first API call)
   */
  async initializeSession(): Promise<SessionInfo> {
    try {
      const response = await this.client.post('/session/init');
      const sessionInfo = response.data;
      
      if (sessionInfo.sessionToken) {
        this.saveSessionToStorage(sessionInfo.sessionToken);
      }
      
      return sessionInfo;
    } catch (error) {
      throw error;
    }
  }

  /**
   * Get current user information
   */
  async getUserInfo(): Promise<UserInfo> {
    try {
      const response = await this.client.get('/user/info');
      return response.data;
    } catch (error) {
      throw error;
    }
  }

  /**
   * Update user settings
   */
  async updateUserSettings(settings: Partial<UserInfo['settings']>): Promise<boolean> {
    try {
      const response = await this.client.put('/user/settings', { settings });
      return response.data.success;
    } catch (error) {
      throw error;
    }
  }

  /**
   * Upload document for OCR processing
   */
  async uploadDocument(
    file: File,
    settings: {
      language: string;
      dpi: number;
      psm: number;
      fastMode: boolean;
      skipTables: boolean;
    }
  ): Promise<{ documentId: string; message: string }> {
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('settings', JSON.stringify(settings));

      const response = await this.client.post('/documents/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        // Long timeout for file upload
        timeout: 300000, // 5 minutes
      });

      return response.data;
    } catch (error) {
      throw error;
    }
  }

  /**
   * Get document processing status
   */
  async getDocumentStatus(documentId: string): Promise<{
    documentId: string;
    status: string;
    progress: number;
    currentPage: number;
    totalPages: number;
    confidence: number;
    estimatedTimeRemaining: number;
    error?: string;
  }> {
    try {
      const response = await this.client.get(`/documents/${documentId}/status`);
      return response.data;
    } catch (error) {
      throw error;
    }
  }

  /**
   * List user's documents
   */
  async listDocuments(
    offset: number = 0,
    limit: number = 20,
    status?: string
  ): Promise<{
    documents: Array<{
      id: string;
      filename: string;
      status: string;
      pages: number;
      confidence: number;
      createdAt: string;
      completedAt?: string;
      originalSize: number;
    }>;
    total: number;
    offset: number;
    limit: number;
  }> {
    try {
      const params = new URLSearchParams({
        offset: offset.toString(),
        limit: limit.toString(),
      });
      
      if (status) {
        params.append('status', status);
      }

      const response = await this.client.get(`/documents?${params}`);
      return response.data;
    } catch (error) {
      throw error;
    }
  }

  /**
   * Download processed document
   */
  async downloadDocument(
    documentId: string,
    format: 'txt' | 'json' | 'csv' | 'pdf'
  ): Promise<Blob> {
    try {
      const response = await this.client.get(`/documents/${documentId}/download/${format}`, {
        responseType: 'blob',
      });

      return response.data;
    } catch (error) {
      throw error;
    }
  }

  /**
   * Delete document
   */
  async deleteDocument(documentId: string): Promise<boolean> {
    try {
      await this.client.delete(`/documents/${documentId}`);
      return true;
    } catch (error) {
      throw error;
    }
  }

  /**
   * Get processing queue status
   */
  async getQueueStatus(): Promise<{
    queueLength: number;
    estimatedWaitTime: number;
    activeWorkers: number;
  }> {
    try {
      const response = await this.client.get('/processing/queue-status');
      return response.data;
    } catch (error) {
      throw error;
    }
  }

  /**
   * Get rate limit information
   */
  getRateLimitInfo(): RateLimitInfo | null {
    return this.rateLimitInfo;
  }

  /**
   * Check if user has valid session
   */
  hasValidSession(): boolean {
    return !!this.sessionToken;
  }

  /**
   * Invalidate current session
   */
  async logout(): Promise<void> {
    try {
      if (this.sessionToken) {
        await this.client.post('/session/invalidate');
      }
    } catch (error) {
      // Continue with logout even if API call fails
      console.warn('Failed to invalidate session on server:', error);
    } finally {
      this.removeSessionFromStorage();
    }
  }
}

// Create singleton instance
const apiClient = new ApiClient();

// Export singleton and class for testing
export default apiClient;
export { ApiClient };