import React from 'react';
import { FileText, Download, Eye, Trash2, Calendar, Award } from 'lucide-react';
import { cn } from '../utils/cn';
import type { Document } from '../types/ocr.types';

interface DocumentCardProps {
  document: Document;
  onView?: (document: Document) => void;
  onDownload?: (document: Document) => void;
  onDelete?: (document: Document) => void;
  variant?: 'grid' | 'list';
  className?: string;
}

export const DocumentCard: React.FC<DocumentCardProps> = ({
  document,
  onView,
  onDownload,
  onDelete,
  variant = 'grid',
  className
}) => {
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  const getStatusColor = (status: Document['status']) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 text-green-800';
      case 'processing':
        return 'bg-blue-100 text-blue-800';
      case 'pending':
        return 'bg-yellow-100 text-yellow-800';
      case 'error':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getConfidenceColor = (confidence?: number) => {
    if (!confidence) return 'text-gray-500';
    if (confidence >= 90) return 'text-green-600';
    if (confidence >= 70) return 'text-yellow-600';
    return 'text-red-600';
  };

  const GridView = () => (
    <div className={cn(
      'bg-white border border-gray-200 rounded-lg overflow-hidden hover:shadow-md transition-shadow duration-200',
      className
    )}>
      {/* Header */}
      <div className="p-4 border-b border-gray-100">
        <div className="flex items-start justify-between">
          <div className="flex items-start space-x-3">
            <div className="flex-shrink-0">
              <FileText className="w-8 h-8 text-red-500" />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-sm font-medium text-gray-900 truncate" title={document.filename}>
                {document.filename}
              </h3>
              <p className="text-xs text-gray-500 mt-1">
                {document.pages} pages • {formatFileSize(document.originalSize)}
              </p>
            </div>
          </div>
          
          <span className={cn(
            'px-2 py-1 text-xs font-medium rounded-full',
            getStatusColor(document.status)
          )}>
            {document.status}
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Stats */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center space-x-2">
            <Calendar className="w-4 h-4 text-gray-400" />
            <div>
              <p className="text-xs text-gray-500">Created</p>
              <p className="text-xs font-medium text-gray-900">
                {new Date(document.createdAt).toLocaleDateString()}
              </p>
            </div>
          </div>
          
          {document.confidence && (
            <div className="flex items-center space-x-2">
              <Award className="w-4 h-4 text-gray-400" />
              <div>
                <p className="text-xs text-gray-500">Confidence</p>
                <p className={cn('text-xs font-medium', getConfidenceColor(document.confidence))}>
                  {document.confidence.toFixed(1)}%
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Settings */}
        <div className="flex items-center space-x-4 text-xs text-gray-500">
          <span>{document.language.toUpperCase()}</span>
          <span>•</span>
          <span>{document.dpi} DPI</span>
          {document.fastMode && (
            <>
              <span>•</span>
              <span className="text-blue-600 font-medium">Fast Mode</span>
            </>
          )}
        </div>
      </div>

      {/* Actions */}
      {document.status === 'completed' && (
        <div className="px-4 pb-4">
          <div className="flex items-center space-x-2">
            {onView && (
              <button
                onClick={() => onView(document)}
                className="flex-1 inline-flex items-center justify-center px-3 py-2 border border-gray-300 shadow-sm text-xs font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
              >
                <Eye className="w-3 h-3 mr-1" />
                View
              </button>
            )}
            {onDownload && (
              <button
                onClick={() => onDownload(document)}
                className="flex-1 inline-flex items-center justify-center px-3 py-2 border border-transparent text-xs font-medium rounded-md text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
              >
                <Download className="w-3 h-3 mr-1" />
                Download
              </button>
            )}
            {onDelete && (
              <button
                onClick={() => onDelete(document)}
                className="inline-flex items-center justify-center px-3 py-2 border border-transparent text-xs font-medium rounded-md text-red-600 bg-red-50 hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );

  const ListView = () => (
    <div className={cn(
      'bg-white border border-gray-200 rounded-lg p-4 hover:shadow-sm transition-shadow duration-200',
      className
    )}>
      <div className="flex items-center justify-between min-w-0">
        <div className="flex items-center space-x-4 flex-1 min-w-0 overflow-hidden">
          <FileText className="w-8 h-8 text-red-500 flex-shrink-0" />
          
          <div className="flex-1 min-w-0 overflow-hidden">
            <h3 className="text-sm font-medium text-gray-900 truncate" title={document.filename}>
              {document.filename}
            </h3>
            <div className="flex items-center flex-wrap gap-x-4 gap-y-1 mt-1 text-xs text-gray-500">
              <span className="whitespace-nowrap">{document.pages} pages</span>
              <span>•</span>
              <span className="whitespace-nowrap">{formatFileSize(document.originalSize)}</span>
              <span>•</span>
              <span className="whitespace-nowrap">{new Date(document.createdAt).toLocaleDateString()}</span>
              {document.confidence && (
                <>
                  <span>•</span>
                  <span className={cn("whitespace-nowrap", getConfidenceColor(document.confidence))}>
                    {document.confidence.toFixed(1)}% confidence
                  </span>
                </>
              )}
            </div>
          </div>
          
          <div className="flex items-center space-x-2 flex-shrink-0">
            <span className={cn(
              'px-2 py-1 text-xs font-medium rounded-full whitespace-nowrap',
              getStatusColor(document.status)
            )}>
              {document.status}
            </span>
            
            {document.fastMode && (
              <span className="px-2 py-1 text-xs font-medium rounded-full bg-blue-100 text-blue-800 whitespace-nowrap">
                Fast Mode
              </span>
            )}
          </div>
        </div>

        {/* Actions */}
        {document.status === 'completed' && (
          <div className="flex items-center space-x-2 ml-4 flex-shrink-0">
            {onView && (
              <button
                onClick={() => onView(document)}
                className="inline-flex items-center px-3 py-1.5 border border-gray-300 shadow-sm text-xs font-medium rounded text-gray-700 bg-white hover:bg-gray-50"
                title="View document"
              >
                <Eye className="w-3 h-3 mr-1" />
                View
              </button>
            )}
            {onDownload && (
              <button
                onClick={() => onDownload(document)}
                className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded text-white bg-red-600 hover:bg-red-700"
                title="Download results"
              >
                <Download className="w-3 h-3 mr-1" />
                Download
              </button>
            )}
            {onDelete && (
              <button
                onClick={() => onDelete(document)}
                className="inline-flex items-center px-2 py-1.5 border border-transparent text-xs font-medium rounded text-red-600 hover:bg-red-50"
                title="Delete document"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );

  return variant === 'grid' ? <GridView /> : <ListView />;
};