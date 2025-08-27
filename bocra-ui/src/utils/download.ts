import type { Document } from '../types/ocr.types';
import type { DownloadFormat } from '../components/DownloadModal';

// Mock OCR result data for generating downloads
const generateMockOCRData = (document: Document) => {
  return {
    documentId: document.id,
    filename: document.filename,
    pages: document.pages,
    confidence: document.confidence || 95.2,
    language: document.language,
    dpi: document.dpi,
    fastMode: document.fastMode,
    processedAt: document.completedAt || new Date(),
    words: Array.from({ length: 500 }, (_, i) => ({
      page: Math.floor(i / 50) + 1,
      text: ['The', 'quick', 'brown', 'fox', 'jumps', 'over', 'the', 'lazy', 'dog'][i % 9],
      confidence: Math.random() * 30 + 70, // 70-100% confidence
      left: Math.random() * 800,
      top: Math.random() * 1000 + (Math.floor(i / 50) * 1100),
      width: Math.random() * 100 + 50,
      height: 20
    })),
    tables: [
      {
        page: 1,
        rows: [
          ['Header 1', 'Header 2', 'Header 3'],
          ['Row 1 Col 1', 'Row 1 Col 2', 'Row 1 Col 3'],
          ['Row 2 Col 1', 'Row 2 Col 2', 'Row 2 Col 3']
        ]
      }
    ],
    text: `Sample OCR Output for ${document.filename}

This is a sample text extraction from your document. In a real implementation, this would contain the actual extracted text from your scanned PDF.

Key Features:
- High accuracy OCR processing
- Structured data extraction
- Confidence scoring for each word
- Table detection and extraction
- Multi-language support

Document Statistics:
- Pages: ${document.pages}
- Average Confidence: ${(document.confidence || 95.2).toFixed(1)}%
- Language: ${document.language.toUpperCase()}
- Resolution: ${document.dpi} DPI
- Fast Mode: ${document.fastMode ? 'Enabled' : 'Disabled'}

This sample demonstrates the quality of text extraction you can expect from BÖCRA's OCR processing engine.`
  };
};

// Generate mock file content based on format
const generateFileContent = (document: Document, format: DownloadFormat['id']): string | ArrayBuffer => {
  const ocrData = generateMockOCRData(document);

  switch (format) {
    case 'txt':
      return ocrData.text;

    case 'json':
      return JSON.stringify({
        metadata: {
          documentId: ocrData.documentId,
          filename: ocrData.filename,
          pages: ocrData.pages,
          confidence: ocrData.confidence,
          language: ocrData.language,
          dpi: ocrData.dpi,
          fastMode: ocrData.fastMode,
          processedAt: ocrData.processedAt.toISOString()
        },
        words: ocrData.words,
        tables: ocrData.tables,
        fullText: ocrData.text
      }, null, 2);

    case 'csv':
      const csvHeaders = ['page', 'text', 'confidence', 'left', 'top', 'width', 'height'];
      const csvRows = ocrData.words.map(word => [
        word.page,
        `"${word.text.replace(/"/g, '""')}"`,
        word.confidence.toFixed(2),
        word.left.toFixed(0),
        word.top.toFixed(0),
        word.width.toFixed(0),
        word.height.toFixed(0)
      ]);
      
      return [
        csvHeaders.join(','),
        ...csvRows.map(row => row.join(','))
      ].join('\n');

    case 'pdf':
      // For PDF, we'll return a placeholder string that indicates a PDF would be generated
      // In a real implementation, you'd use a library like jsPDF or PDFKit
      return `%PDF-1.4
% Mock PDF content for ${document.filename}
% This is a placeholder for a searchable PDF with OCR text layer
% In a real implementation, this would be a proper PDF binary
Sample PDF Content - ${ocrData.text.substring(0, 200)}...`;

    default:
      throw new Error(`Unsupported format: ${format}`);
  }
};

// Get MIME type for the download format
const getMimeType = (format: DownloadFormat['id']): string => {
  switch (format) {
    case 'txt':
      return 'text/plain';
    case 'json':
      return 'application/json';
    case 'csv':
      return 'text/csv';
    case 'pdf':
      return 'application/pdf';
    default:
      return 'application/octet-stream';
  }
};

// Get file extension for the format
const getFileExtension = (format: DownloadFormat['id']): string => {
  switch (format) {
    case 'txt':
      return '.txt';
    case 'json':
      return '.json';
    case 'csv':
      return '.csv';
    case 'pdf':
      return '.pdf';
    default:
      return '.bin';
  }
};

// Main download function
export const downloadDocument = async (
  document: Document,
  format: DownloadFormat['id']
): Promise<void> => {
  try {
    // Simulate processing delay for better UX
    await new Promise(resolve => setTimeout(resolve, 1000));

    const content = generateFileContent(document, format);
    const mimeType = getMimeType(format);
    const extension = getFileExtension(format);
    
    // Generate filename without extension, then add the correct extension
    const baseFilename = document.filename.replace(/\.[^/.]+$/, '');
    const filename = `${baseFilename}_ocr${extension}`;

    // Create blob and download
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);

    // Create temporary download link
    const link = window.document.createElement('a');
    link.href = url;
    link.download = filename;
    link.style.display = 'none';

    window.document.body.appendChild(link);
    link.click();
    window.document.body.removeChild(link);

    // Clean up
    URL.revokeObjectURL(url);

  } catch (error) {
    console.error('Download failed:', error);
    throw error;
  }
};

// Utility to format file size
export const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
};

// Utility to validate download capability
export const canDownload = (document: Document): boolean => {
  return document.status === 'completed';
};