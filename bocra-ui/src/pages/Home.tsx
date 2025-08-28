import React, { useState, useEffect } from 'react';
import { Zap, FileText, Download, Award, ArrowRight, User, Shield, AlertCircle } from 'lucide-react';
import { FileUploader } from '../components/FileUploader';
import { OCRSettings } from '../components/OCRSettings';
import { ProcessingStatus } from '../components/ProcessingStatus';
import { DocumentCard } from '../components/DocumentCard';
import { DownloadModal } from '../components/DownloadModal';
import { downloadDocument } from '../utils/download';
import { useSession } from '../hooks/useSession';
import apiClient from '../utils/api';
import type { OCRConfig as OCRSettingsType, Document, ProcessingStatus as ProcessingStatusType } from '../types/ocr.types';
import type { DownloadFormat } from '../components/DownloadModal';

export const Home: React.FC = () => {
  // Session management
  const { userInfo, isLoading: sessionLoading, isAuthenticated, error: sessionError, refreshUserInfo, clearError } = useSession();
  
  // UI state
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadProgress, setUploadProgress] = useState<Array<{ filename: string; progress: number; status: 'ready' | 'uploading' | 'completed' | 'error' }>>([]);
  const [ocrSettings, setOcrSettings] = useState<OCRSettingsType>({
    language: 'eng',
    dpi: 400,
    psm: 1,
    fastMode: false,
    skipTables: false
  });
  
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStatus, setProcessingStatus] = useState<ProcessingStatusType | null>(null);
  const [downloadModalOpen, setDownloadModalOpen] = useState(false);
  const [documentToDownload, setDocumentToDownload] = useState<Document | null>(null);
  const [recentDocuments, setRecentDocuments] = useState<Document[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  
  // Load user settings when available
  useEffect(() => {
    if (userInfo?.settings) {
      setOcrSettings({
        language: userInfo.settings.language,
        dpi: userInfo.settings.dpi,
        psm: userInfo.settings.psm,
        fastMode: userInfo.settings.fastMode,
        skipTables: userInfo.settings.skipTables
      });
    }
  }, [userInfo]);
  
  // Load recent documents when authenticated
  useEffect(() => {
    if (isAuthenticated && !documentsLoading) {
      loadRecentDocuments();
    }
  }, [isAuthenticated]);
  
  const loadRecentDocuments = async () => {
    if (!isAuthenticated) return;
    
    setDocumentsLoading(true);
    try {
      const response = await apiClient.listDocuments(0, 5); // Get 5 most recent
      setRecentDocuments(response.documents.map(doc => ({
        id: doc.id,
        filename: doc.filename,
        originalSize: doc.originalSize,
        pages: doc.pages,
        status: doc.status as any,
        createdAt: new Date(doc.createdAt),
        completedAt: doc.completedAt ? new Date(doc.completedAt) : undefined,
        confidence: doc.confidence,
        language: 'eng', // Default as backend doesn't return this yet
        dpi: 400, // Default as backend doesn't return this yet
        fastMode: false // Default as backend doesn't return this yet
      })));
    } catch (error) {
      console.error('Failed to load recent documents:', error);
      // Fall back to mock data for now
      setRecentDocuments([
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
        }
      ]);
    } finally {
      setDocumentsLoading(false);
    }
  };

  const handleFilesSelected = (files: File[]) => {
    setSelectedFiles(files);
    // Initialize upload progress
    const newProgress = files.map(file => ({
      filename: file.name,
      progress: 0,
      status: 'ready' as const
    }));
    setUploadProgress(newProgress);
  };

  const handleFileRemove = (filename: string) => {
    setSelectedFiles(prev => prev.filter(f => f.name !== filename));
    setUploadProgress(prev => prev.filter(p => p.filename !== filename));
  };

  const handleStartProcessing = async () => {
    if (selectedFiles.length === 0 || !isAuthenticated) return;
    
    setIsProcessing(true);
    
    try {
      // Upload the first file (for now)
      const file = selectedFiles[0];
      
      // Update status to uploading
      setUploadProgress(prev => 
        prev.map(p => 
          p.filename === file.name 
            ? { ...p, status: 'uploading' as const }
            : p
        )
      );
      
      const uploadResult = await apiClient.uploadDocument(file, ocrSettings);
      
      console.log('Upload successful:', uploadResult);
      
      // Update status to completed
      setUploadProgress(prev => 
        prev.map(p => 
          p.filename === file.name 
            ? { ...p, status: 'completed' as const, progress: 100 }
            : p
        )
      );
      
      // Start polling for processing status
      pollProcessingStatus(uploadResult.documentId);
    } catch (error) {
      console.error('Upload failed:', error);
      
      // Update status to error
      if (selectedFiles.length > 0) {
        setUploadProgress(prev => 
          prev.map(p => 
            p.filename === selectedFiles[0].name 
              ? { ...p, status: 'error' as const }
              : p
          )
        );
      }
      
      setIsProcessing(false);
      // TODO: Show error notification
      return;
    }
  };
  
  const pollProcessingStatus = async (documentId: string) => {
    const pollInterval = setInterval(async () => {
      try {
        const status = await apiClient.getDocumentStatus(documentId);
        
        setProcessingStatus({
          documentId: status.documentId,
          currentPage: status.currentPage,
          totalPages: status.totalPages,
          progress: status.progress,
          estimatedTimeRemaining: status.estimatedTimeRemaining,
          averageConfidence: status.confidence
        });
        
        // Stop polling when complete
        if (status.status === 'completed' || status.status === 'error') {
          clearInterval(pollInterval);
          setIsProcessing(false);
          
          if (status.status === 'completed') {
            // Refresh document list
            await loadRecentDocuments();
            await refreshUserInfo(); // Update storage stats
          }
        }
      } catch (error) {
        console.error('Failed to poll processing status:', error);
        clearInterval(pollInterval);
        setIsProcessing(false);
      }
    }, 2000); // Poll every 2 seconds
  };

  const handleViewDocument = (document: Document) => {
    console.log('View document:', document);
    // TODO: Implement document viewer
  };

  const handleDownloadDocument = (document: Document) => {
    setDocumentToDownload(document);
    setDownloadModalOpen(true);
  };

  const handleDeleteDocument = async (document: Document) => {
    if (!isAuthenticated) return;
    
    try {
      await apiClient.deleteDocument(document.id);
      // Refresh document list
      await loadRecentDocuments();
      await refreshUserInfo(); // Update storage stats
    } catch (error) {
      console.error('Delete failed:', error);
      // TODO: Show error notification
    }
  };

  const handleDownloadModalClose = () => {
    setDownloadModalOpen(false);
    setDocumentToDownload(null);
  };

  const handleDownloadFormat = async (document: Document, format: DownloadFormat['id']) => {
    if (!isAuthenticated) return;
    
    try {
      // Try to download from API first
      const blob = await apiClient.downloadDocument(document.id, format);
      
      // Create download link
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement('a');
      link.href = url;
      
      const extension = format === 'txt' ? '.txt' : format === 'json' ? '.json' : format === 'csv' ? '.csv' : '.pdf';
      link.download = `${document.filename.replace(/\.[^/.]+$/, '')}_ocr${extension}`;
      
      link.style.display = 'none';
      window.document.body.appendChild(link);
      link.click();
      window.document.body.removeChild(link);
      URL.revokeObjectURL(url);
      
    } catch (error) {
      console.error('API download failed, falling back to mock:', error);
      // Fall back to mock download
      await downloadDocument(document, format);
    }
  };

  const handleProcessingDownload = () => {
    if (!processingStatus) return;
    
    // Create a mock document from processing status
    const mockDocument: Document = {
      id: processingStatus.documentId,
      filename: selectedFiles[0]?.name || 'processed_document.pdf',
      originalSize: selectedFiles[0]?.size || 0,
      pages: processingStatus.totalPages,
      status: 'completed',
      createdAt: new Date(),
      completedAt: new Date(),
      confidence: processingStatus.averageConfidence,
      language: ocrSettings.language,
      dpi: ocrSettings.dpi,
      fastMode: ocrSettings.fastMode
    };
    
    handleDownloadDocument(mockDocument);
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
              <span className="text-red-600">BÖCRA</span>
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

      {/* Session Status Bar */}
      {sessionError && (
        <div className="bg-red-50 border-b border-red-200">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
            <div className="flex items-center">
              <AlertCircle className="w-5 h-5 text-red-600 mr-3" />
              <div className="flex-1">
                <p className="text-sm text-red-800">{sessionError.message}</p>
              </div>
              <button
                onClick={clearError}
                className="text-red-600 hover:text-red-800 text-sm font-medium"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      )}


      {/* User Info Bar */}
      {isAuthenticated && userInfo && (
        <div className="bg-blue-50 border-b border-blue-200">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-4">
                <div className="flex items-center">
                  <Shield className="w-4 h-4 text-blue-600 mr-2" />
                  <span className="text-sm text-blue-800">
                    Secure Session Active
                  </span>
                </div>
                <div className="text-sm text-blue-700">
                  {userInfo.documentCount} documents • {(userInfo.storageUsedBytes / 1024 / 1024).toFixed(1)} MB used
                </div>
              </div>
              <div className="text-sm text-blue-700">
                {userInfo.quotaUsedPercent.toFixed(1)}% of quota used
              </div>
            </div>
          </div>
        </div>
      )}

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
                  disabled={isProcessing || !isAuthenticated}
                  externalProgress={uploadProgress}
                  onFileRemove={handleFileRemove}
                />
                
                {!isAuthenticated && (
                  <div className="mt-4 p-4 bg-gray-50 rounded-md">
                    <div className="flex items-center">
                      <User className="w-5 h-5 text-gray-400 mr-2" />
                      <p className="text-sm text-gray-600">
                        {sessionLoading ? 'Initializing secure session...' : 'Secure session required for uploads'}
                      </p>
                    </div>
                  </div>
                )}
                
                {selectedFiles.length > 0 && !isProcessing && isAuthenticated && (
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
              <ProcessingStatus 
                status={processingStatus} 
                onDownload={handleProcessingDownload}
              />
            )}

            {/* OCR Settings */}
            <OCRSettings
              settings={ocrSettings}
              onSettingsChange={setOcrSettings}
              disabled={isProcessing || !isAuthenticated}
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
                  {documentsLoading ? (
                    <div className="text-center py-8">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-600 mx-auto"></div>
                      <p className="text-sm text-gray-500 mt-2">Loading documents...</p>
                    </div>
                  ) : recentDocuments.length > 0 ? (
                    recentDocuments.map((document) => (
                      <DocumentCard
                        key={document.id}
                        document={document}
                        variant="list"
                        onView={handleViewDocument}
                        onDownload={handleDownloadDocument}
                        onDelete={handleDeleteDocument}
                      />
                    ))
                  ) : isAuthenticated ? (
                    <div className="text-center py-8">
                      <FileText className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                      <p className="text-sm text-gray-500">No documents yet. Upload your first PDF to get started!</p>
                    </div>
                  ) : (
                    <div className="text-center py-8">
                      <User className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                      <p className="text-sm text-gray-500">Please wait while we initialize your secure session...</p>
                    </div>
                  )}
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

      {/* Download Modal */}
      {downloadModalOpen && documentToDownload && (
        <DownloadModal
          isOpen={downloadModalOpen}
          onClose={handleDownloadModalClose}
          document={documentToDownload}
          onDownload={handleDownloadFormat}
        />
      )}
    </div>
  );
};