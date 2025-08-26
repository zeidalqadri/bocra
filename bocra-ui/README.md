# BOCRA UI

A modern, responsive web interface for the BOCRA (High-Fidelity OCR) tool.

## Features

- 🚀 **Fast Processing**: Real-time OCR processing with progress tracking
- 📁 **Drag & Drop Upload**: Easy file upload with support for multiple PDFs
- ⚙️ **Configurable Settings**: Customizable OCR parameters (language, DPI, fast mode)
- 📊 **Processing Status**: Live updates with progress bars and time estimates
- 📄 **Document Management**: View, download, and manage processed documents
- 🎨 **Modern Design**: Clean, professional interface inspired by document collaboration tools
- 📱 **Responsive**: Works perfectly on desktop, tablet, and mobile devices
- ♿ **Accessible**: WCAG 2.1 AA compliant with full keyboard navigation

## Technology Stack

- **Frontend**: React 18 + TypeScript
- **Styling**: Tailwind CSS with custom design system
- **Build Tool**: Vite
- **Components**: Custom component library with shadcn/ui patterns
- **Icons**: Lucide React
- **File Handling**: React Dropzone
- **State Management**: Zustand (when needed)

## Getting Started

### Prerequisites

- Node.js 16+ 
- npm or yarn

### Installation

```bash
# Install dependencies
npm install

# Install additional Tailwind plugins
npm install -D @tailwindcss/forms

# Start development server
npm run dev
```

The application will be available at `http://localhost:3000`.

### Building for Production

```bash
npm run build
```

## Project Structure

```
src/
├── components/          # Reusable UI components
│   ├── FileUploader.tsx
│   ├── OCRSettings.tsx
│   ├── ProcessingStatus.tsx
│   └── DocumentCard.tsx
├── pages/              # Page components
│   └── Home.tsx
├── types/              # TypeScript type definitions
│   └── ocr.types.ts
├── utils/              # Utility functions
│   └── cn.ts
├── styles/             # Global styles
│   └── globals.css
├── App.tsx
└── main.tsx
```

## Components

### FileUploader
- Drag & drop interface for PDF uploads
- File validation and error handling
- Upload progress tracking
- Multiple file support

### OCRSettings
- Language selection (50+ languages)
- DPI/resolution configuration  
- Fast mode toggle (10x speed boost)
- Page segmentation mode options
- Advanced settings (table detection, etc.)

### ProcessingStatus
- Real-time progress tracking
- Processing speed metrics
- Confidence scoring
- Time estimates and completion status

### DocumentCard
- Document preview with metadata
- Status indicators and confidence scores
- Action buttons (view, download, delete)
- Grid and list view modes

## Design System

### Colors
- Primary: Red (#EF4444) - CTAs and important elements
- Secondary: Dark Gray (#374151) - Text and headers  
- Background: White (#FFFFFF) - Main content areas
- Surface: Light Gray (#F9FAFB) - Cards and sections

### Typography
- Font: Inter (Google Fonts)
- Headings: 600-700 weight
- Body: 400-500 weight
- Code: JetBrains Mono

### Component Patterns
- Card-based layouts for content organization
- Red accent colors for primary actions
- Consistent spacing using Tailwind scale
- Hover states and smooth transitions
- Loading states with skeleton components

## API Integration

The UI is designed to work with the BOCRA Python backend via REST API:

```typescript
// Example API calls
POST /api/upload       # Upload PDF files
GET  /api/process/:id  # Get processing status  
GET  /api/documents    # List processed documents
GET  /api/document/:id # Get document details
```

## Features in Detail

### Upload Flow
1. User drags/selects PDF files
2. Files are validated (type, size)
3. Upload progress is displayed
4. Files are queued for processing

### Processing Flow  
1. User configures OCR settings
2. Processing starts with real-time updates
3. Progress bar shows current page/total
4. Confidence scores are calculated
5. Results are ready for download

### Document Management
- Grid/list view toggle
- Search and filtering
- Batch operations
- Export options (JSON, CSV, searchable PDF)

## Accessibility

- Semantic HTML structure
- ARIA labels and roles
- Keyboard navigation support
- High contrast colors (WCAG AA)
- Screen reader optimization
- Focus management

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Mobile)

## Contributing

1. Follow the existing code style
2. Use TypeScript for type safety
3. Add proper ARIA labels for accessibility
4. Test on multiple devices/browsers
5. Update documentation as needed

## License

MIT License - see LICENSE file for details.