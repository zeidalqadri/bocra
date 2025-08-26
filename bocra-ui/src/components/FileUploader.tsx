import React, { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, FileText, X } from 'lucide-react';
import { cn } from '../utils/cn';
import type { UploadProgress } from '../types/ocr.types';

interface FileUploaderProps {
  onFilesSelected: (files: File[]) => void;
  maxFiles?: number;
  maxSize?: number;
  accept?: string;
  disabled?: boolean;
  className?: string;
}

export const FileUploader: React.FC<FileUploaderProps> = ({
  onFilesSelected,
  maxFiles = 10,
  maxSize = 50 * 1024 * 1024, // 50MB
  accept = '.pdf',
  disabled = false,
  className
}) => {
  const [uploadProgress, setUploadProgress] = useState<UploadProgress[]>([]);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (disabled) return;
    
    const newProgress = acceptedFiles.map(file => ({
      filename: file.name,
      progress: 0,
      status: 'uploading' as const
    }));
    
    setUploadProgress(newProgress);
    onFilesSelected(acceptedFiles);
  }, [onFilesSelected, disabled]);

  const {
    getRootProps,
    getInputProps,
    isDragActive,
    isDragReject,
    fileRejections
  } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf']
    },
    maxFiles,
    maxSize,
    disabled
  });

  const removeFile = (filename: string) => {
    setUploadProgress(prev => prev.filter(p => p.filename !== filename));
  };

  return (
    <div className={cn('space-y-4', className)}>
      {/* Drop Zone */}
      <div
        {...getRootProps()}
        className={cn(
          'border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-all duration-200',
          'hover:border-red-400 hover:bg-red-50',
          isDragActive && 'border-red-500 bg-red-50',
          isDragReject && 'border-red-600 bg-red-100',
          disabled && 'opacity-50 cursor-not-allowed'
        )}
      >
        <input {...getInputProps()} />
        
        <div className="flex flex-col items-center space-y-4">
          <div className={cn(
            'w-16 h-16 rounded-full flex items-center justify-center',
            'bg-gray-100 transition-colors',
            isDragActive && 'bg-red-100'
          )}>
            <Upload className={cn(
              'w-8 h-8 text-gray-400',
              isDragActive && 'text-red-500'
            )} />
          </div>
          
          <div className="space-y-2">
            <h3 className="text-lg font-semibold text-gray-900">
              {isDragActive ? 'Drop your PDFs here' : 'Upload PDF Documents'}
            </h3>
            <p className="text-sm text-gray-600">
              Drag and drop your PDFs here, or{' '}
              <span className="text-red-600 font-medium">browse files</span>
            </p>
            <p className="text-xs text-gray-500">
              Max {maxFiles} files, up to {Math.round(maxSize / 1024 / 1024)}MB each
            </p>
          </div>
        </div>
      </div>

      {/* File Rejections */}
      {fileRejections.length > 0 && (
        <div className="space-y-2">
          {fileRejections.map(({ file, errors }) => (
            <div key={file.name} className="bg-red-50 border border-red-200 rounded-md p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <FileText className="w-4 h-4 text-red-500" />
                  <span className="text-sm font-medium text-red-800">{file.name}</span>
                </div>
              </div>
              <div className="mt-1">
                {errors.map(error => (
                  <p key={error.code} className="text-xs text-red-600">
                    {error.message}
                  </p>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Upload Progress */}
      {uploadProgress.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-gray-900">Uploaded Files</h4>
          {uploadProgress.map((progress) => (
            <div key={progress.filename} className="bg-gray-50 border border-gray-200 rounded-md p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <FileText className="w-4 h-4 text-green-500" />
                  <span className="text-sm font-medium text-gray-900">
                    {progress.filename}
                  </span>
                  <span className={cn(
                    'px-2 py-1 text-xs rounded-full',
                    progress.status === 'completed' && 'bg-green-100 text-green-800',
                    progress.status === 'uploading' && 'bg-blue-100 text-blue-800',
                    progress.status === 'error' && 'bg-red-100 text-red-800'
                  )}>
                    {progress.status}
                  </span>
                </div>
                <button
                  onClick={() => removeFile(progress.filename)}
                  className="text-gray-400 hover:text-gray-600"
                  aria-label="Remove file"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};