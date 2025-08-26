import React from 'react';
import { Clock, Cpu, CheckCircle, AlertCircle, Loader } from 'lucide-react';
import { cn } from '../utils/cn';
import type { ProcessingStatus as ProcessingStatusType } from '../types/ocr.types';

interface ProcessingStatusProps {
  status: ProcessingStatusType;
  className?: string;
}

export const ProcessingStatus: React.FC<ProcessingStatusProps> = ({
  status,
  className
}) => {
  const progressPercentage = Math.round(status.progress);
  const isCompleted = progressPercentage >= 100;
  
  const formatTime = (seconds?: number): string => {
    if (!seconds) return 'Calculating...';
    
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    
    if (mins > 0) {
      return `${mins}m ${secs}s`;
    }
    return `${secs}s`;
  };

  return (
    <div className={cn(
      'bg-white border border-gray-200 rounded-lg p-6 space-y-4',
      className
    )}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          {isCompleted ? (
            <CheckCircle className="w-5 h-5 text-green-600" />
          ) : (
            <Loader className="w-5 h-5 text-blue-600 animate-spin" />
          )}
          <h3 className="text-lg font-semibold text-gray-900">
            {isCompleted ? 'Processing Complete' : 'Processing Document'}
          </h3>
        </div>
        <span className="text-sm text-gray-500">
          {status.documentId.slice(0, 8)}...
        </span>
      </div>

      {/* Progress Bar */}
      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <span className="text-sm font-medium text-gray-700">
            Page {status.currentPage} of {status.totalPages}
          </span>
          <span className="text-sm text-gray-600">
            {progressPercentage}%
          </span>
        </div>
        
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className={cn(
              'h-2 rounded-full transition-all duration-300',
              isCompleted ? 'bg-green-600' : 'bg-blue-600'
            )}
            style={{ width: `${progressPercentage}%` }}
          />
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
        {/* Time Remaining */}
        <div className="flex items-center space-x-3">
          <div className="flex-shrink-0">
            <Clock className="w-5 h-5 text-gray-500" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-900">
              {isCompleted ? 'Completed' : 'Time Remaining'}
            </p>
            <p className="text-xs text-gray-600">
              {isCompleted 
                ? 'Processing finished' 
                : formatTime(status.estimatedTimeRemaining)
              }
            </p>
          </div>
        </div>

        {/* Processing Speed */}
        <div className="flex items-center space-x-3">
          <div className="flex-shrink-0">
            <Cpu className="w-5 h-5 text-gray-500" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-900">Processing Rate</p>
            <p className="text-xs text-gray-600">
              {status.currentPage > 0 
                ? `${(status.currentPage / Math.max(1, (Date.now() - Date.now()) / 1000) * 60).toFixed(1)} pages/min`
                : 'Starting...'
              }
            </p>
          </div>
        </div>

        {/* Confidence Score */}
        <div className="flex items-center space-x-3">
          <div className="flex-shrink-0">
            {status.averageConfidence && status.averageConfidence >= 90 ? (
              <CheckCircle className="w-5 h-5 text-green-500" />
            ) : status.averageConfidence && status.averageConfidence >= 70 ? (
              <AlertCircle className="w-5 h-5 text-yellow-500" />
            ) : (
              <AlertCircle className="w-5 h-5 text-red-500" />
            )}
          </div>
          <div>
            <p className="text-sm font-medium text-gray-900">Avg. Confidence</p>
            <p className="text-xs text-gray-600">
              {status.averageConfidence 
                ? `${status.averageConfidence.toFixed(1)}%`
                : 'Calculating...'
              }
            </p>
          </div>
        </div>
      </div>

      {/* Status Messages */}
      <div className="pt-2 border-t border-gray-200">
        {isCompleted ? (
          <div className="flex items-center space-x-2 text-green-700">
            <CheckCircle className="w-4 h-4" />
            <span className="text-sm font-medium">
              Document processed successfully! Ready for download.
            </span>
          </div>
        ) : (
          <div className="flex items-center space-x-2 text-blue-700">
            <Loader className="w-4 h-4 animate-spin" />
            <span className="text-sm">
              Processing page {status.currentPage} of {status.totalPages}...
            </span>
          </div>
        )}
      </div>

      {/* Progress Details */}
      {!isCompleted && status.estimatedTimeRemaining && (
        <div className="bg-blue-50 border border-blue-200 rounded-md p-3">
          <div className="flex items-start space-x-2">
            <Cpu className="w-4 h-4 text-blue-600 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-blue-900">
                Processing Status
              </p>
              <p className="text-xs text-blue-700 mt-1">
                Current page: {status.currentPage}/{status.totalPages} • 
                Progress: {progressPercentage}% • 
                ETA: {formatTime(status.estimatedTimeRemaining)}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};