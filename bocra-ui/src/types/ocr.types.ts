export interface Document {
  id: string;
  filename: string;
  originalSize: number;
  pages: number;
  status: 'pending' | 'processing' | 'completed' | 'error';
  createdAt: Date;
  completedAt?: Date;
  confidence?: number;
  language: string;
  dpi: number;
  fastMode: boolean;
}

export interface OCRSettings {
  language: string;
  dpi: number;
  psm: number;
  fastMode: boolean;
  skipTables: boolean;
}

export interface ProcessingStatus {
  documentId: string;
  currentPage: number;
  totalPages: number;
  progress: number;
  estimatedTimeRemaining?: number;
  averageConfidence?: number;
}

export interface OCRResult {
  structured: any;
  words: Array<{
    page: number;
    text: string;
    confidence: number;
    left: number;
    top: number;
    width: number;
    height: number;
  }>;
  searchablePdf?: string;
  qualityReport: {
    overallAvgConfidence: number;
    lowConfPages: number[];
  };
}

export interface UploadProgress {
  filename: string;
  progress: number;
  status: 'uploading' | 'completed' | 'error';
}