/**
 * React hook for session management and IP tracking
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import apiClient, { SessionInfo, UserInfo, ApiError } from '../utils/api';

interface SessionState {
  sessionInfo: SessionInfo | null;
  userInfo: UserInfo | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  error: ApiError | null;
}

interface SessionActions {
  initializeSession: () => Promise<void>;
  refreshUserInfo: () => Promise<void>;
  updateSettings: (settings: Partial<UserInfo['settings']>) => Promise<boolean>;
  logout: () => Promise<void>;
  clearError: () => void;
}

export interface UseSessionResult extends SessionState, SessionActions {}

/**
 * Custom hook for managing user sessions and IP-based authentication
 */
export const useSession = (): UseSessionResult => {
  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const initializeRef = useRef(false);

  // Derived state
  const isAuthenticated = !!sessionInfo?.sessionToken && sessionInfo.isActive;

  /**
   * Initialize session - called automatically on mount
   */
  const initializeSession = useCallback(async () => {
    // Prevent multiple simultaneous initialization attempts
    if (initializeRef.current) return;
    initializeRef.current = true;

    setIsLoading(true);
    setError(null);

    try {
      // Check if we already have a valid session
      if (apiClient.hasValidSession()) {
        // Try to get user info to validate the session
        const userInfoResponse = await apiClient.getUserInfo();
        setUserInfo(userInfoResponse);
        
        // If successful, we have a valid session
        setSessionInfo({
          sessionToken: 'existing', // We don't expose the actual token
          ipHash: userInfoResponse.ipHash,
          expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(), // Assume 24h expiry
          isActive: true,
        });
      } else {
        // Initialize new session
        const newSession = await apiClient.initializeSession();
        setSessionInfo(newSession);

        // Get user info for the new session
        const userInfoResponse = await apiClient.getUserInfo();
        setUserInfo(userInfoResponse);
      }
    } catch (err) {
      const apiError = err as ApiError;
      console.error('Backend connection failed:', apiError.message);
      
      // Set error without falling back to demo mode
      setError({
        message: `Backend connection failed: ${apiError.message}`,
        status: apiError.status,
        code: apiError.code || 'CONNECTION_ERROR',
      });
    } finally {
      setIsLoading(false);
      initializeRef.current = false;
    }
  }, []);

  /**
   * Refresh user information
   */
  const refreshUserInfo = useCallback(async () => {
    if (!isAuthenticated) return;

    setIsLoading(true);
    setError(null);

    try {
      const userInfoResponse = await apiClient.getUserInfo();
      setUserInfo(userInfoResponse);
    } catch (err) {
      const apiError = err as ApiError;
      setError(apiError);
      console.error('Failed to refresh user info:', apiError);
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated]);

  /**
   * Update user settings
   */
  const updateSettings = useCallback(async (
    settings: Partial<UserInfo['settings']>
  ): Promise<boolean> => {
    if (!isAuthenticated) return false;

    setIsLoading(true);
    setError(null);

    try {
      const success = await apiClient.updateUserSettings(settings);
      
      if (success) {
        // Refresh user info to get updated settings
        await refreshUserInfo();
      }
      
      return success;
    } catch (err) {
      const apiError = err as ApiError;
      setError(apiError);
      console.error('Failed to update settings:', apiError);
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, refreshUserInfo]);

  /**
   * Logout and clear session
   */
  const logout = useCallback(async () => {
    setIsLoading(true);

    try {
      await apiClient.logout();
    } catch (err) {
      console.warn('Error during logout:', err);
    } finally {
      // Clear state regardless of API call success
      setSessionInfo(null);
      setUserInfo(null);
      setError(null);
      setIsLoading(false);
    }
  }, []);

  /**
   * Clear current error
   */
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Initialize session on mount
  useEffect(() => {
    initializeSession();
  }, [initializeSession]);

  // Set up event listeners for auth errors and rate limiting
  useEffect(() => {
    const handleAuthError = (event: CustomEvent<ApiError>) => {
      console.error('Authentication error:', event.detail);
      setError(event.detail);
      setSessionInfo(null);
      setUserInfo(null);
    };

    const handleRateLimited = (event: CustomEvent) => {
      console.warn('Rate limited:', event.detail);
      setError({
        message: 'Too many requests. Please wait before trying again.',
        status: 429,
        code: 'RATE_LIMITED',
        details: event.detail,
      });
    };

    window.addEventListener('bocra:auth-error', handleAuthError as EventListener);
    window.addEventListener('bocra:rate-limited', handleRateLimited as EventListener);

    return () => {
      window.removeEventListener('bocra:auth-error', handleAuthError as EventListener);
      window.removeEventListener('bocra:rate-limited', handleRateLimited as EventListener);
    };
  }, []);

  // Auto-refresh user info periodically
  useEffect(() => {
    if (!isAuthenticated) return;

    const interval = setInterval(() => {
      refreshUserInfo();
    }, 5 * 60 * 1000); // Refresh every 5 minutes

    return () => clearInterval(interval);
  }, [isAuthenticated, refreshUserInfo]);

  return {
    // State
    sessionInfo,
    userInfo,
    isLoading,
    isAuthenticated,
    error,

    // Actions
    initializeSession,
    refreshUserInfo,
    updateSettings,
    logout,
    clearError,
  };
};