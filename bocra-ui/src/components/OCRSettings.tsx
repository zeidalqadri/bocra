import React from 'react';
import { Settings, Zap, Languages, Monitor } from 'lucide-react';
import { cn } from '../utils/cn';
import type { OCRSettings } from '../types/ocr.types';

interface OCRSettingsProps {
  settings: OCRSettings;
  onSettingsChange: (settings: OCRSettings) => void;
  disabled?: boolean;
  className?: string;
}

const languageOptions = [
  { value: 'eng', label: 'English' },
  { value: 'eng+fra', label: 'English + French' },
  { value: 'eng+spa', label: 'English + Spanish' },
  { value: 'eng+msa', label: 'English + Malay' },
  { value: 'ara', label: 'Arabic' },
  { value: 'chi_sim', label: 'Chinese (Simplified)' },
  { value: 'chi_tra', label: 'Chinese (Traditional)' }
];

const dpiOptions = [
  { value: 200, label: '200 DPI (Fast)' },
  { value: 250, label: '250 DPI (Balanced)' },
  { value: 300, label: '300 DPI (Good)' },
  { value: 400, label: '400 DPI (High Quality)' },
  { value: 500, label: '500 DPI (Maximum)' }
];

const psmOptions = [
  { value: 1, label: 'Auto with OSD' },
  { value: 4, label: 'Single column text' },
  { value: 6, label: 'Single uniform block' },
  { value: 8, label: 'Single word' },
  { value: 13, label: 'Raw line (no formatting)' }
];

export const OCRSettings: React.FC<OCRSettingsProps> = ({
  settings,
  onSettingsChange,
  disabled = false,
  className
}) => {
  const updateSetting = <K extends keyof OCRSettings>(
    key: K,
    value: OCRSettings[K]
  ) => {
    onSettingsChange({
      ...settings,
      [key]: value
    });
  };

  return (
    <div className={cn(
      'bg-white border border-gray-200 rounded-lg p-6 space-y-6',
      disabled && 'opacity-50 pointer-events-none',
      className
    )}>
      <div className="flex items-center space-x-2">
        <Settings className="w-5 h-5 text-gray-600" />
        <h3 className="text-lg font-semibold text-gray-900">OCR Settings</h3>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Fast Mode Toggle */}
        <div className="space-y-2">
          <label className="flex items-center space-x-2 text-sm font-medium text-gray-700">
            <Zap className="w-4 h-4" />
            <span>Fast Mode</span>
          </label>
          <div className="flex items-center space-x-3">
            <button
              type="button"
              onClick={() => updateSetting('fastMode', !settings.fastMode)}
              className={cn(
                'relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2',
                settings.fastMode ? 'bg-red-600' : 'bg-gray-200'
              )}
              role="switch"
              aria-checked={settings.fastMode}
            >
              <span
                className={cn(
                  'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out',
                  settings.fastMode ? 'translate-x-5' : 'translate-x-0'
                )}
              />
            </button>
            <span className="text-xs text-gray-500">
              {settings.fastMode ? '10x faster' : 'High accuracy'}
            </span>
          </div>
        </div>

        {/* Language Selection */}
        <div className="space-y-2">
          <label className="flex items-center space-x-2 text-sm font-medium text-gray-700">
            <Languages className="w-4 h-4" />
            <span>Language</span>
          </label>
          <select
            value={settings.language}
            onChange={(e) => updateSetting('language', e.target.value)}
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-red-500 focus:ring-red-500 text-sm"
          >
            {languageOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/* DPI Selection */}
        <div className="space-y-2">
          <label className="flex items-center space-x-2 text-sm font-medium text-gray-700">
            <Monitor className="w-4 h-4" />
            <span>Resolution</span>
          </label>
          <select
            value={settings.dpi}
            onChange={(e) => updateSetting('dpi', Number(e.target.value))}
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-red-500 focus:ring-red-500 text-sm"
            disabled={settings.fastMode} // Fast mode overrides DPI
          >
            {dpiOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {settings.fastMode && (
            <p className="text-xs text-gray-500">Auto-adjusted for fast mode</p>
          )}
        </div>

        {/* PSM Selection */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-gray-700">
            Page Segmentation
          </label>
          <select
            value={settings.psm}
            onChange={(e) => updateSetting('psm', Number(e.target.value))}
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-red-500 focus:ring-red-500 text-sm"
          >
            {psmOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Advanced Options */}
      <div className="pt-4 border-t border-gray-200">
        <h4 className="text-sm font-medium text-gray-900 mb-3">Advanced Options</h4>
        <div className="flex items-center space-x-4">
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={settings.skipTables}
              onChange={(e) => updateSetting('skipTables', e.target.checked)}
              className="rounded border-gray-300 text-red-600 shadow-sm focus:border-red-500 focus:ring-red-500"
            />
            <span className="text-sm text-gray-700">Skip table detection</span>
          </label>
        </div>
        <p className="text-xs text-gray-500 mt-2">
          Enable for faster processing if tables are not needed
        </p>
      </div>

      {/* Settings Summary */}
      {settings.fastMode && (
        <div className="bg-green-50 border border-green-200 rounded-md p-3">
          <div className="flex items-center space-x-2">
            <Zap className="w-4 h-4 text-green-600" />
            <span className="text-sm font-medium text-green-800">
              Fast Mode Enabled
            </span>
          </div>
          <p className="text-xs text-green-600 mt-1">
            Processing will be ~10x faster with optimized settings
          </p>
        </div>
      )}
    </div>
  );
};