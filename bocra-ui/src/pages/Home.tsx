import React, { useState } from 'react';
import { Zap, FileText, Download, Award, ArrowRight } from 'lucide-react';
import { FileUploader } from '../components/FileUploader';
import { OCRSettings } from '../components/OCRSettings';
import { ProcessingStatus } from '../components/ProcessingStatus';
import { DocumentCard } from '../components/DocumentCard';
import type { OCRSettings as OCRSettingsType, Document, ProcessingStatus as ProcessingStatusType } from '../types/ocr.types';

export const Home: React.FC = () => {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [ocrSettings, setOcrSettings] = useState<OCRSettingsType>({
    language: 'eng',
    dpi: 400,
    psm: 1,
    fastMode: false,
    skipTables: false
  });
  
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStatus, setProcessingStatus] = useState<ProcessingStatusType | null>(null);
  
  // Mock data for recent documents
  const [recentDocuments] = useState<Document[]>([
    {
      id: '1',
      filename: 'basketball_coaching_manual_level1.pdf',
      originalSize: 5242880,
      pages: 101,
      status: 'completed',
      createdAt: new Date('2024-01-20'),
      completedAt: new Date('2024-01-20'),
      confidence: 95.2,
      language: 'eng',
      dpi: 300,
      fastMode: true
    },
    {
      id: '2', 
      filename: 'research_paper_draft.pdf',
      originalSize: 2097152,
      pages: 24,
      status: 'completed',
      createdAt: new Date('2024-01-19'),
      completedAt: new Date('2024-01-19'),
      confidence: 87.3,
      language: 'eng',
      dpi: 400,
      fastMode: false
    },
    {
      id: '3',
      filename: 'scanned_invoice_batch.pdf',
      originalSize: 1048576,
      pages: 5,
      status: 'processing',
      createdAt: new Date('2024-01-21'),
      language: 'eng',
      dpi: 300,
      fastMode: true
    }
  ]);

  const handleFilesSelected = (files: File[]) => {
    setSelectedFiles(files);
  };

  const handleStartProcessing = () => {
    if (selectedFiles.length === 0) return;
    
    setIsProcessing(true);
    // Mock processing status
    setProcessingStatus({
      documentId: 'doc-' + Date.now(),
      currentPage: 1,
      totalPages: 101,
      progress: 0,
      estimatedTimeRemaining: 120,
      averageConfidence: 0
    });

    // Simulate processing progress
    const interval = setInterval(() => {
      setProcessingStatus(prev => {
        if (!prev) return null;
        
        const newProgress = Math.min(prev.progress + 2, 100);
        const newPage = Math.floor((newProgress / 100) * prev.totalPages);
        
        if (newProgress >= 100) {
          clearInterval(interval);
          setIsProcessing(false);
          return {
            ...prev,
            currentPage: prev.totalPages,
            progress: 100,
            estimatedTimeRemaining: 0,
            averageConfidence: 94.8
          };
        }
        
        return {
          ...prev,
          currentPage: newPage,
          progress: newProgress,
          estimatedTimeRemaining: Math.round((100 - newProgress) * 1.2),
          averageConfidence: 85 + (newProgress / 100) * 10
        };
      });
    }, 500);
  };

  const handleViewDocument = (document: Document) => {
    console.log('View document:', document);
  };

  const handleDownloadDocument = (document: Document) => {
    console.log('Download document:', document);
  };

  const handleDeleteDocument = (document: Document) => {
    console.log('Delete document:', document);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Hero Section */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
          <div className="text-center">
            <div className="flex justify-center mb-6">
              <div className="flex items-center space-x-2 bg-red-100 px-4 py-2 rounded-full">
                <Zap className="w-5 h-5 text-red-600" />
                <span className="text-red-800 font-medium text-sm">10x Faster OCR</span>
              </div>
            </div>
            
            <h1 className="text-4xl font-bold text-gray-900 sm:text-5xl">
              High-Fidelity OCR for
              <span className="text-red-600"> Scanned PDFs</span>
            </h1>
            
            <p className="mt-4 text-xl text-gray-600 max-w-3xl mx-auto">
              Transform your scanned documents into searchable, editable text with industry-leading accuracy.
              Fast mode delivers results in minutes, not hours.
            </p>

            <div className="mt-8 flex justify-center space-x-8">
              <div className="text-center">
                <div className="text-2xl font-bold text-gray-900">95.2%</div>
                <div className="text-sm text-gray-600">Average Accuracy</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-gray-900">10x</div>
                <div className="text-sm text-gray-600">Faster Processing</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-gray-900">50+</div>
                <div className="text-sm text-gray-600">Languages Supported</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left Column - Upload & Settings */}
          <div className="lg:col-span-2 space-y-6">
            {/* File Upload */}
            <div className="bg-white rounded-lg shadow-sm">
              <div className="p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">
                  Upload Documents
                </h2>
                <FileUploader
                  onFilesSelected={handleFilesSelected}
                  maxFiles={10}
                  disabled={isProcessing}
                />
                
                {selectedFiles.length > 0 && !isProcessing && (
                  <div className="mt-6 flex justify-end">
                    <button
                      onClick={handleStartProcessing}
                      className="inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-md text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 transition-colors"
                    >
                      Start OCR Processing
                      <ArrowRight className="ml-2 w-5 h-5" />
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Processing Status */}
            {processingStatus && (
              <ProcessingStatus status={processingStatus} />
            )}

            {/* OCR Settings */}
            <OCRSettings
              settings={ocrSettings}
              onSettingsChange={setOcrSettings}
              disabled={isProcessing}
            />
          </div>

          {/* Right Column - Recent Documents */}
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-sm">
              <div className="p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">
                  Recent Documents
                </h2>
                
                <div className="space-y-4">
                  {recentDocuments.map((document) => (
                    <DocumentCard
                      key={document.id}
                      document={document}
                      variant="list"
                      onView={handleViewDocument}
                      onDownload={handleDownloadDocument}
                      onDelete={handleDeleteDocument}
                    />
                  ))}
                </div>

                <div className="mt-6 text-center">
                  <button className="text-sm text-red-600 hover:text-red-700 font-medium">
                    View all documents →
                  </button>
                </div>
              </div>
            </div>

            {/* Feature Highlights */}
            <div className="bg-white rounded-lg shadow-sm">
              <div className="p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">
                  Why Choose BOCRA?
                </h3>
                
                <div className="space-y-4">
                  <div className="flex items-start space-x-3">
                    <Zap className="w-5 h-5 text-red-500 mt-0.5" />
                    <div>
                      <h4 className="text-sm font-medium text-gray-900">Fast Mode</h4>
                      <p className="text-xs text-gray-600">
                        Process documents 10x faster with optimized settings
                      </p>
                    </div>
                  </div>
                  
                  <div className="flex items-start space-x-3">
                    <Award className="w-5 h-5 text-red-500 mt-0.5" />
                    <div>
                      <h4 className="text-sm font-medium text-gray-900">High Accuracy</h4>
                      <p className="text-xs text-gray-600">
                        Industry-leading 95%+ accuracy with confidence scoring
                      </p>
                    </div>
                  </div>
                  
                  <div className="flex items-start space-x-3">
                    <FileText className="w-5 h-5 text-red-500 mt-0.5" />
                    <div>
                      <h4 className="text-sm font-medium text-gray-900">Multiple Formats</h4>
                      <p className="text-xs text-gray-600">
                        Export as searchable PDF, JSON, CSV, or plain text
                      </p>
                    </div>
                  </div>
                  
                  <div className="flex items-start space-x-3">
                    <Download className="w-5 h-5 text-red-500 mt-0.5" />
                    <div>
                      <h4 className="text-sm font-medium text-gray-900">Easy Export</h4>
                      <p className="text-xs text-gray-600">
                        Download results in your preferred format instantly
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};