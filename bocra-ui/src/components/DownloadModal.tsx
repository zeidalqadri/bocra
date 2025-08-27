import React, { useState } from 'react';
import { X, Download, FileText, Database, Table, Code } from 'lucide-react';
import { cn } from '../utils/cn';
import type { Document } from '../types/ocr.types';

export interface DownloadFormat {
  id: 'pdf' | 'json' | 'csv' | 'txt';
  name: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  extension: string;
}

const DOWNLOAD_FORMATS: DownloadFormat[] = [
  {
    id: 'pdf',
    name: 'Searchable PDF',
    description: 'Original document with searchable text layer',
    icon: FileText,
    extension: '.pdf'
  },
  {
    id: 'json',
    name: 'JSON Data',
    description: 'Structured data with coordinates and confidence scores',
    icon: Code,
    extension: '.json'
  },
  {
    id: 'csv',
    name: 'CSV Export',
    description: 'Tabular data for spreadsheet applications',
    icon: Table,
    extension: '.csv'
  },
  {
    id: 'txt',
    name: 'Plain Text',
    description: 'Clean text without formatting',
    icon: Database,
    extension: '.txt'
  }
];

interface DownloadModalProps {
  isOpen: boolean;
  onClose: () => void;
  document: Document;
  onDownload: (document: Document, format: DownloadFormat['id']) => void;
}

export const DownloadModal: React.FC<DownloadModalProps> = ({
  isOpen,
  onClose,
  document,
  onDownload
}) => {
  const [selectedFormat, setSelectedFormat] = useState<DownloadFormat['id']>('pdf');
  const [isDownloading, setIsDownloading] = useState(false);

  if (!isOpen) return null;

  const handleDownload = async () => {
    setIsDownloading(true);
    try {
      await onDownload(document, selectedFormat);
      onClose();
    } catch (error) {
      console.error('Download failed:', error);
    } finally {
      setIsDownloading(false);
    }
  };

  const selectedFormatInfo = DOWNLOAD_FORMATS.find(f => f.id === selectedFormat);

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-gray-200">
            <div>
              <h3 className="text-lg font-semibold text-gray-900">
                Download Document
              </h3>
              <p className="text-sm text-gray-600 mt-1 truncate">
                {document.filename}
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 rounded-md p-1"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content */}
          <div className="p-6 space-y-4">
            <div>
              <h4 className="text-sm font-medium text-gray-900 mb-3">
                Select Format
              </h4>
              <div className="space-y-2">
                {DOWNLOAD_FORMATS.map((format) => {
                  const Icon = format.icon;
                  return (
                    <label
                      key={format.id}
                      className={cn(
                        'flex items-start space-x-3 p-3 border rounded-lg cursor-pointer transition-colors',
                        selectedFormat === format.id
                          ? 'border-red-500 bg-red-50'
                          : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                      )}
                    >
                      <input
                        type="radio"
                        name="format"
                        value={format.id}
                        checked={selectedFormat === format.id}
                        onChange={() => setSelectedFormat(format.id)}
                        className="mt-1 w-4 h-4 text-red-600 border-gray-300 focus:ring-red-500"
                      />
                      <Icon className={cn(
                        'w-5 h-5 mt-0.5',
                        selectedFormat === format.id ? 'text-red-600' : 'text-gray-400'
                      )} />
                      <div className="flex-1">
                        <div className="text-sm font-medium text-gray-900">
                          {format.name}
                        </div>
                        <div className="text-xs text-gray-600 mt-1">
                          {format.description}
                        </div>
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>

            {/* File Info */}
            <div className="bg-gray-50 rounded-lg p-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600">File will be saved as:</span>
                <span className="font-medium text-gray-900">
                  {document.filename.replace(/\.[^/.]+$/, '')}{selectedFormatInfo?.extension}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm mt-2">
                <span className="text-gray-600">Document pages:</span>
                <span className="font-medium text-gray-900">{document.pages}</span>
              </div>
              {document.confidence && (
                <div className="flex items-center justify-between text-sm mt-2">
                  <span className="text-gray-600">Average confidence:</span>
                  <span className="font-medium text-gray-900">
                    {document.confidence.toFixed(1)}%
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end space-x-3 p-6 border-t border-gray-200">
            <button
              onClick={onClose}
              disabled={isDownloading}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
            <button
              onClick={handleDownload}
              disabled={isDownloading}
              className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-red-600 border border-transparent rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isDownloading ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                  Downloading...
                </>
              ) : (
                <>
                  <Download className="w-4 h-4 mr-2" />
                  Download
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};