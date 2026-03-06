'use client';

import { useState, useEffect, useRef } from 'react';
import { api, type ContentStatus, type ScrapeStatus, type ScrapeConfig, type AIInfo } from '@/lib/api';
import { ScrapingStatusCard } from '@/components/crawler/ScrapingStatusCard';
import { CollapsibleConfigPanel } from '@/components/crawler/CollapsibleConfigPanel';
import { IndexProgressCard } from '@/components/crawler/IndexProgressCard';
import { SchedulerStatusCard } from '@/components/crawler/SchedulerStatusCard';
import { PerformanceMetricsCard } from '@/components/admin/PerformanceMetricsCard';

// ============== Type Definitions ==============

interface DbStats {
  documents: number;
  chunks: number;
  index_type: string;
  embedding_model: string;
}

// ============== Tab Components ==============

// Tab 1: Content Status
function ContentStatusTab() {
  const [loading, setLoading] = useState(true);
  const [content, setContent] = useState<ContentStatus | null>(null);
  const [dbStats, setDbStats] = useState<DbStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAllValid, setShowAllValid] = useState(false);
  const [showAllInvalid, setShowAllInvalid] = useState(false);
  const [showAllPdfs, setShowAllPdfs] = useState(false);

  const fetchContent = async () => {
    setLoading(true);
    setError(null);
    try {
      // Fetch both content status and db stats in parallel
      const [contentResponse, dbResponse] = await Promise.all([
        api.getContentStatus(),
        api.getDbStats(),
      ]);

      if (contentResponse.success && contentResponse.data) {
        setContent(contentResponse.data);
      } else {
        setError(contentResponse.error || 'Failed to fetch content status');
      }

      // Log db stats response for debugging
      console.log('DB Stats response:', dbResponse);

      if (dbResponse.success && dbResponse.data) {
        setDbStats(dbResponse.data as DbStats);
      } else if (dbResponse.error) {
        console.error('DB Stats error:', dbResponse.error);
        // Don't fail the entire tab if db stats fail, just log it
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchContent();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-3 text-gray-800">Loading...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
        <p className="text-red-800">{error}</p>
        <button
          onClick={fetchContent}
          className="mt-2 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!content) return null;

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg shadow p-6">
          <div className="text-sm text-gray-800">Valid Files</div>
          <div className="text-3xl font-bold text-green-600">{content.total_trunked_files}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <div className="text-sm text-gray-800">Invalid Files</div>
          <div className="text-3xl font-bold text-red-600">{content.total_invalid_files}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <div className="text-sm text-gray-800">PDF Files</div>
          <div className="text-3xl font-bold text-blue-600">{content.total_pdfs}</div>
        </div>
      </div>

      {/* Database Statistics Card */}
      {dbStats && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Database Statistics</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-purple-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-purple-600">{dbStats.chunks}</div>
              <div className="text-sm text-gray-800">Total Chunks</div>
            </div>
            <div className="bg-indigo-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-indigo-600">{dbStats.documents}</div>
              <div className="text-sm text-gray-800">Documents</div>
            </div>
            <div className="bg-gray-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-gray-800">{dbStats.index_type || 'HNSW'}</div>
              <div className="text-sm text-gray-800">Index Type</div>
            </div>
          </div>
        </div>
      )}

      {/* Valid Files */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Valid Files List</h3>
          <button
            onClick={() => setShowAllValid(!showAllValid)}
            className="text-sm text-blue-600 hover:underline"
          >
            {showAllValid ? 'Collapse' : 'Expand All'}
          </button>
        </div>
        <div className="max-h-64 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 sticky top-0">
              <tr>
                <th className="text-left p-2 text-gray-900">Filename</th>
                <th className="text-right p-2 text-gray-900">Size</th>
                <th className="text-left p-2 text-gray-900">Path</th>
              </tr>
            </thead>
            <tbody>
              {(showAllValid ? content.valid_trunked_files : content.valid_trunked_files.slice(0, 10)).map((file, i) => (
                <tr key={i} className="border-t">
                  <td className="p-2 text-gray-900">{file.name}</td>
                  <td className="p-2 text-right text-gray-900">{file.size.toLocaleString()} chars</td>
                  <td className="p-2 text-gray-900 truncate max-w-xs">{file.path}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Invalid Files */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Invalid Files List</h3>
          <button
            onClick={() => setShowAllInvalid(!showAllInvalid)}
            className="text-sm text-blue-600 hover:underline"
          >
            {showAllInvalid ? 'Collapse' : 'Expand All'}
          </button>
        </div>
        {content.invalid_files.length === 0 ? (
          <p className="text-gray-800">No invalid files</p>
        ) : (
          <div className="max-h-64 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="text-left p-2 text-gray-900">Filename</th>
                  <th className="text-right p-2 text-gray-900">Size</th>
                  <th className="text-left p-2 text-gray-900">Reason</th>
                </tr>
              </thead>
              <tbody>
                {(showAllInvalid ? content.invalid_files : content.invalid_files.slice(0, 10)).map((file, i) => (
                  <tr key={i} className="border-t">
                    <td className="p-2 text-gray-900">{file.name}</td>
                    <td className="p-2 text-right text-gray-900">{file.size} chars</td>
                    <td className="p-2 text-red-500">{file.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* PDF Files */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-gray-900">PDF Files List</h3>
          <button
            onClick={() => setShowAllPdfs(!showAllPdfs)}
            className="text-sm text-blue-600 hover:underline"
          >
            {showAllPdfs ? 'Collapse' : 'Expand All'}
          </button>
        </div>
        {content.pdf_files.length === 0 ? (
          <p className="text-gray-800">No PDF files</p>
        ) : (
          <div className="max-h-64 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="text-left p-2 text-gray-900">Filename</th>
                  <th className="text-right p-2 text-gray-900">Size</th>
                </tr>
              </thead>
              <tbody>
                {(showAllPdfs ? content.pdf_files : content.pdf_files.slice(0, 10)).map((file, i) => (
                  <tr key={i} className="border-t">
                    <td className="p-2 text-gray-900">{file.name}</td>
                    <td className="p-2 text-right text-gray-900">{(file.size / 1024 / 1024).toFixed(2)} MB</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Refresh Button */}
      <div className="flex justify-center">
        <button
          onClick={fetchContent}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          Refresh Status
        </button>
      </div>
    </div>
  );
}

// Unified Crawler Management Section
function CrawlerManagementSection() {
  const [indexing, setIndexing] = useState(false);
  const [indexProgress, setIndexProgress] = useState(0);
  const [indexFiles, setIndexFiles] = useState({ processed: 0, total: 0 });
  const [scrapeRunning, setScrapeRunning] = useState(false);

  // Check scrape status on mount - in case scrape was triggered by scheduler
  useEffect(() => {
    checkScrapeStatusOnMount();
  }, []);

  async function checkScrapeStatusOnMount() {
    try {
      const response = await api.getScrapeStatus();
      if (response.success && response.data?.is_running) {
        console.log('[Crawler] Scrape already running on mount');
        setScrapeRunning(true);
      }
    } catch (error) {
      console.error('Failed to check scrape status on mount:', error);
    }
  }

  async function handleIndex() {
    setIndexing(true);
    setIndexProgress(0);

    try {
      // Monitor progress
      const checkProgress = setInterval(async () => {
        const progressResponse = await api.getIndexProgress();
        if (progressResponse.success && progressResponse.data) {
          const progress = progressResponse.data;
          setIndexProgress(progress.progress_percent);
          setIndexFiles({
            processed: progress.processed_files,
            total: progress.files_to_process,
          });

          if (progress.status === 'complete') {
            clearInterval(checkProgress);
            setIndexing(false);
            setIndexProgress(100);
          }
        }
      }, 1000);

      // Trigger indexing
      await api.indexNewFiles();
    } catch (error) {
      console.error('Index failed:', error);
      setIndexing(false);
    }
  }

  async function handleStopScrape() {
    try {
      const response = await api.stopScrape();
      if (response.success) {
        setScrapeRunning(false);
      }
    } catch (error) {
      console.error('Failed to stop scrape:', error);
    }
  }

  return (
    <div className="space-y-6">
      <ScrapingStatusCard
        onIndex={handleIndex}
        indexing={indexing}
        indexProgress={indexProgress}
        onScrapeRunningChange={setScrapeRunning}
        onStopScrape={handleStopScrape}
        scrapeRunning={scrapeRunning}
      />

      <SchedulerStatusCard scrapeRunning={scrapeRunning} />

      <CollapsibleConfigPanel />

      {indexing && (
        <IndexProgressCard
          inProgress={indexing}
          progress={indexProgress}
          filesProcessed={indexFiles.processed}
          totalFiles={indexFiles.total}
        />
      )}
    </div>
  );
}

// Tab 5: File Upload
function FileUploadTab() {
  const [files, setFiles] = useState<File[]>([]);
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'uploaded' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState<string>('');
  const [counts, setCounts] = useState<{ pdfTexts: number; pages: number; external: number; total: number } | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Indexing state
  const [indexStatus, setIndexStatus] = useState<'idle' | 'indexing' | 'complete' | 'error'>('idle');
  const [indexMessage, setIndexMessage] = useState<string>('');
  const [indexProgress, setIndexProgress] = useState<{
    status: string;
    current_file: string;
    total_chunks: number;
    processed_chunks: number;
    files_to_process: number;
    processed_files: number;
    progress_percent: number;
    error_message: string;
  } | null>(null);
  const [showIndexPrompt, setShowIndexPrompt] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<string[]>([]);

  const checkStatus = async () => {
    try {
      const response = await fetch('/api/upload-data');
      const data = await response.json();

      if (data.status === 'ok') {
        setCounts({
          pdfTexts: data.counts.pdfTexts || 0,
          pages: data.counts.pages || 0,
          external: data.counts.external || 0,
          total: data.total || 0,
        });
        setMessage(`Found ${data.total} files on server`);
      }
    } catch (error) {
      setMessage(`Error: ${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles(Array.from(e.target.files));
    }
  };

  const handleUpload = async () => {
    if (files.length === 0) {
      setMessage('Please select files to upload');
      return;
    }

    setUploadStatus('uploading');
    setMessage(`Uploading ${files.length} file(s)...`);
    setUploadProgress(0);

    try {
      // Separate PDF files from text files
      const pdfFiles: File[] = [];
      const textFiles: File[] = [];
      const uploadedFilePaths: string[] = [];

      for (const file of files) {
        const fileName = file.name.toLowerCase();
        if (fileName.endsWith('.pdf')) {
          pdfFiles.push(file);
        } else {
          textFiles.push(file);
        }
      }

      let pdfUploadSuccess = true;
      let textUploadSuccess = true;
      let pdfError = '';
      let textError = '';

      // Upload PDF files
      if (pdfFiles.length > 0) {
        for (const pdf of pdfFiles) {
          try {
            const formData = new FormData();
            formData.append('file', pdf);

            const response = await fetch('/api/admin/upload-pdf', {
              method: 'POST',
              body: formData,
            });

            const data = await response.json();

            if (!response.ok || !data.success) {
              pdfUploadSuccess = false;
              pdfError = data.error || data.data?.error || 'PDF upload failed';
              break;
            }

            // Store path for indexing (PDFs go to scraped/pdfs/)
            uploadedFilePaths.push(`./data/input/scraped/pdfs/${pdf.name}`);
          } catch (error) {
            pdfUploadSuccess = false;
            pdfError = error instanceof Error ? error.message : String(error);
            break;
          }
        }
      }

      // Upload text files
      if (textFiles.length > 0) {
        const formData = new FormData();

        for (const file of textFiles) {
          const fileName = file.name.toLowerCase();
          let folder = 'pages';

          if (fileName.includes('pdf') && (fileName.endsWith('.txt') || fileName.match(/_[a-f0-9]+\.txt$/))) {
            folder = 'pdf-texts';
          } else if (fileName.includes('external') || fileName.includes('wp-content') || fileName.includes('http')) {
            folder = 'external';
          }

          formData.append(`${folder}/${file.name}`, file);
          // Store expected file path for indexing
          uploadedFilePaths.push(`./data/input/scraped/${folder}/${file.name}`);
        }

        const response = await fetch('/api/upload-data', {
          method: 'POST',
          body: formData,
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
          textUploadSuccess = false;
          textError = data.error || data.message || 'Text file upload failed';
        }
      }

      setUploadProgress(100);

      // Check overall status
      if (!pdfUploadSuccess || !textUploadSuccess) {
        setUploadStatus('error');
        const errors = [];
        if (!pdfUploadSuccess && pdfFiles.length > 0) errors.push(`PDF: ${pdfError}`);
        if (!textUploadSuccess && textFiles.length > 0) errors.push(`Text: ${textError}`);
        setMessage(errors.join(' | '));
        setShowIndexPrompt(false);
        return;
      }

      setUploadStatus('uploaded');
      setUploadedFiles(uploadedFilePaths);
      setShowIndexPrompt(true);
      setMessage(`Successfully uploaded ${files.length} file(s). Create index now to make them searchable?`);
      setFiles([]);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      await checkStatus();
    } catch (error) {
      setUploadStatus('error');
      setMessage(`Error: ${error instanceof Error ? error.message : String(error)}`);
      setShowIndexPrompt(false);
    }
  };

  const handleIndexFiles = async () => {
    setShowIndexPrompt(false);
    setIndexStatus('indexing');
    setIndexMessage('Creating index for uploaded files...');

    try {
      // Start polling for progress
      const progressInterval = setInterval(async () => {
        try {
          const response = await api.getIndexProgress();
          if (response.success && response.data) {
            setIndexProgress(response.data as any);
          }
        } catch (e) {
          // Ignore polling errors
        }
      }, 1000);

      // Call index-files endpoint with the uploaded file paths
      const response = await api.indexFiles(uploadedFiles);

      clearInterval(progressInterval);

      if (response.success) {
        setIndexStatus('complete');
        setIndexMessage(response.data?.message || 'Index created successfully!');
        // Refresh content status to show updated chunk count
        setTimeout(() => window.location.reload(), 2000);
      } else {
        setIndexStatus('error');
        setIndexMessage(response.error || 'Indexing failed');
      }
    } catch (error) {
      setIndexStatus('error');
      setIndexMessage(`Error: ${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const handleSkipIndex = () => {
    setShowIndexPrompt(false);
    setIndexMessage('Files uploaded but not indexed. Use "Index New Files" button to create index later.');
  };

  const handleIndexNewFiles = async () => {
    setIndexStatus('indexing');
    setIndexMessage('Scanning for new files and creating index...');

    try {
      // Start polling for progress
      const progressInterval = setInterval(async () => {
        try {
          const response = await api.getIndexProgress();
          if (response.success && response.data) {
            setIndexProgress(response.data as any);
          }
        } catch (e) {
          // Ignore polling errors
        }
      }, 1000);

      const response = await api.indexNewFiles();

      clearInterval(progressInterval);

      if (response.success) {
        setIndexStatus('complete');
        setIndexMessage(response.data?.message || 'Index created successfully!');
        // Refresh to show updated stats
        setTimeout(() => window.location.reload(), 2000);
      } else {
        setIndexStatus('error');
        setIndexMessage(response.error || 'Indexing failed');
      }
    } catch (error) {
      setIndexStatus('error');
      setIndexMessage(`Error: ${error instanceof Error ? error.message : String(error)}`);
    }
  };

  useEffect(() => {
    checkStatus();
  }, []);

  return (
    <div className="space-y-6">
      {/* Current Files Status */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Server File Status</h3>

        <div className="flex gap-2 mb-4">
          <button
            onClick={checkStatus}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Refresh Status
          </button>
        </div>

        {counts && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-blue-600">{counts.pdfTexts}</div>
              <div className="text-sm text-gray-800">PDF Texts</div>
            </div>
            <div className="bg-gray-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-green-600">{counts.pages}</div>
              <div className="text-sm text-gray-800">Pages</div>
            </div>
            <div className="bg-gray-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-purple-600">{counts.external}</div>
              <div className="text-sm text-gray-800">External</div>
            </div>
            <div className="bg-gray-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-gray-800">{counts.total}</div>
              <div className="text-sm text-gray-800">Total</div>
            </div>
          </div>
        )}

        {message && uploadStatus === 'idle' && (
          <div className="mt-4 p-3 bg-blue-50 rounded-lg text-sm text-blue-800">
            {message}
          </div>
        )}
      </div>

      {/* File Upload */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Upload Files</h3>

        <div className="border-2 border-dashed border-gray-300 rounded-lg p-6">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            onChange={handleFileSelect}
            className="block w-full text-sm text-gray-900 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"
            accept=".txt,.html,.json,.pdf"
          />

          {files.length > 0 && (
            <div className="mt-4">
              <p className="text-sm font-semibold text-gray-800 mb-2">
                Selected {files.length} file(s):
              </p>
              <ul className="list-disc list-inside text-sm text-gray-900 max-h-40 overflow-y-auto">
                {files.map((file, idx) => (
                  <li key={idx}>{file.name} ({(file.size / 1024).toFixed(1)} KB)</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Upload Progress */}
        {uploadStatus === 'uploading' && (
          <div className="mt-4">
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-indigo-600 h-2 rounded-full transition-all"
                style={{ width: `${uploadProgress}%` }}
              ></div>
            </div>
            <p className="text-sm text-gray-800 mt-2">Upload Progress: {uploadProgress}%</p>
          </div>
        )}

        {/* Upload Message */}
        {uploadStatus !== 'idle' && uploadStatus !== 'uploading' && message && (
          <div className={`mt-4 rounded-lg p-4 ${
            uploadStatus === 'uploaded' ? 'bg-green-50 text-green-800' :
            uploadStatus === 'success' ? 'bg-green-50 text-green-800' :
            uploadStatus === 'error' ? 'bg-red-50 text-red-800' :
            'bg-blue-50 text-blue-800'
          }`}>
            {message}
          </div>
        )}

        {/* Upload Button */}
        <button
          onClick={handleUpload}
          disabled={files.length === 0 || uploadStatus === 'uploading'}
          className="w-full mt-4 px-6 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
        >
          {uploadStatus === 'uploading' ? 'Uploading...' : `Upload ${files.length} File(s)`}
        </button>

        {/* Instructions */}
        <div className="mt-6 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <p className="text-sm text-yellow-800 mb-2">
            <strong>Instructions:</strong>
          </p>
          <ul className="text-sm text-yellow-800 list-disc list-inside space-y-1">
            <li>Supported file types: <code className="bg-yellow-100 px-1 rounded">.pdf</code>, <code className="bg-yellow-100 px-1 rounded">.txt</code>, <code className="bg-yellow-100 px-1 rounded">.html</code></li>
            <li>PDF files will be saved to <code className="bg-yellow-100 px-1 rounded">scraped/pdfs/</code> directory</li>
            <li>Text/HTML files will be organized into: <code className="bg-yellow-100 px-1 rounded">pdf-texts/</code>, <code className="bg-yellow-100 px-1 rounded">pages/</code>, or <code className="bg-yellow-100 px-1 rounded">external/</code></li>
            <li><strong>After upload, click "Index New Files" to make documents searchable</strong></li>
          </ul>
        </div>
      </div>

      {/* Index Prompt Dialog */}
      {showIndexPrompt && (
        <div className="bg-white rounded-lg shadow p-6 border-2 border-blue-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">📚 Create Index for Uploaded Files?</h3>
          <div className="space-y-4">
            <p className="text-gray-800">
              Files have been uploaded successfully. To make them searchable in the chatbot, you need to create an index.
            </p>
            <div className="bg-blue-50 p-4 rounded-lg">
              <p className="text-sm text-blue-800">
                <strong>What is indexing?</strong><br/>
                Indexing creates embeddings from your documents, enabling the AI to search and retrieve relevant content.
              </p>
            </div>
            <div className="flex gap-4">
              <button
                onClick={handleIndexFiles}
                className="flex-1 px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 font-semibold"
              >
                Yes, Create Index Now
              </button>
              <button
                onClick={handleSkipIndex}
                className="flex-1 px-6 py-3 bg-gray-400 text-white rounded-lg hover:bg-gray-500 font-semibold"
              >
                Skip for Now
              </button>
            </div>
            <p className="text-xs text-gray-800">
              You can always create index later using the "Index New Files" button below.
            </p>
          </div>
        </div>
      )}

      {/* Indexing Progress */}
      {(indexStatus === 'indexing' || indexStatus === 'complete' || indexStatus === 'error') && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Indexing Progress</h3>

          {indexStatus === 'indexing' && indexProgress && (
            <>
              <div className="mb-4">
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-800">
                    {indexProgress.status === 'embedding' ? 'Generating embeddings...' :
                     indexProgress.status === 'indexing' ? 'Updating indices...' :
                     'Processing files...'}
                  </span>
                  <span>{indexProgress.progress_percent}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-green-600 h-2 rounded-full transition-all"
                    style={{ width: `${indexProgress.progress_percent}%` }}
                  ></div>
                </div>
              </div>

              {indexProgress.current_file && (
                <div className="p-3 bg-blue-50 rounded-lg">
                  <div className="text-sm text-gray-800">Processing:</div>
                  <div className="text-sm font-medium break-all">{indexProgress.current_file}</div>
                </div>
              )}

              <div className="grid grid-cols-3 gap-4 text-center">
                <div>
                  <div className="text-2xl font-bold text-blue-600">{indexProgress.processed_files}</div>
                  <div className="text-sm text-gray-800">Files Processed</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-green-600">{indexProgress.processed_chunks}</div>
                  <div className="text-sm text-gray-800">Chunks Processed</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-purple-600">{indexProgress.total_chunks}</div>
                  <div className="text-sm text-gray-800">Total Chunks</div>
                </div>
              </div>
            </>
          )}

          {indexStatus === 'complete' && (
            <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
              <p className="text-green-800 font-semibold">✅ {indexMessage}</p>
            </div>
          )}

          {indexStatus === 'error' && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-red-800">❌ {indexMessage}</p>
            </div>
          )}
        </div>
      )}

      {/* Index New Files Button */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Index Management</h3>
        <p className="text-gray-800 mb-4">
          Scan for and index any new files that haven't been indexed yet.
        </p>
        <button
          onClick={handleIndexNewFiles}
          disabled={indexStatus === 'indexing'}
          className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
        >
          {indexStatus === 'indexing' ? 'Indexing...' : 'Index New Files'}
        </button>
        {indexMessage && !showIndexPrompt && (
          <div className={`mt-4 rounded-lg p-4 ${
            indexStatus === 'complete' ? 'bg-green-50 text-green-800' :
            indexStatus === 'error' ? 'bg-red-50 text-red-800' :
            'bg-blue-50 text-blue-800'
          }`}>
            {indexMessage}
          </div>
        )}
      </div>
    </div>
  );
}

// Tab 6: AI Config
function AIConfigTab() {
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [aiInfo, setAiInfo] = useState<AIInfo | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string; details?: any } | null>(null);

  const fetchAIInfo = async () => {
    setLoading(true);
    try {
      const response = await api.getAIInfo();
      if (response.success && response.data) {
        setAiInfo(response.data);
      }
    } catch (e) {
      console.error('Failed to fetch AI info:', e);
    } finally {
      setLoading(false);
    }
  };

  const testConnection = async () => {
    setTesting(true);
    setMessage(null);
    try {
      const response = await api.testAIConnection('Hello, please respond with "Connection successful"');
      if (response.success && response.data) {
        setMessage({
          type: 'success',
          text: 'AI connection test successful!',
          details: response.data
        });
      } else {
        setMessage({ type: 'error', text: response.error || 'Test failed' });
      }
    } catch (e) {
      setMessage({ type: 'error', text: e instanceof Error ? e.message : String(e) });
    } finally {
      setTesting(false);
    }
  };

  useEffect(() => {
    fetchAIInfo();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-3 text-gray-800">Loading...</span>
      </div>
    );
  }

  if (!aiInfo) return null;

  return (
    <div className="space-y-6">
      {/* AI Info Card */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Current AI Configuration</h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-gray-50 rounded-lg p-4">
            <div className="text-sm text-gray-800">Provider</div>
            <div className="text-xl font-bold text-blue-600">{aiInfo.provider}</div>
          </div>
          <div className="bg-gray-50 rounded-lg p-4">
            <div className="text-sm text-gray-800">Model</div>
            <div className="text-xl font-bold text-gray-900">{aiInfo.model}</div>
          </div>
          <div className="bg-gray-50 rounded-lg p-4 md:col-span-2">
            <div className="text-sm text-gray-800">Base URL</div>
            <div className="text-sm font-mono text-gray-900 break-all">{aiInfo.base_url}</div>
          </div>
          <div className="bg-gray-50 rounded-lg p-4">
            <div className="text-sm text-gray-800">Embedding Model</div>
            <div className="font-medium text-gray-900">{aiInfo.embedding_model}</div>
          </div>
          <div className="bg-gray-50 rounded-lg p-4">
            <div className="text-sm text-gray-800">Embedding Device</div>
            <div className="font-medium text-gray-900">{aiInfo.embedding_device}</div>
          </div>
        </div>
      </div>

      {/* Test Connection Card */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Connection Test</h3>

        <p className="text-gray-800 mb-4">
          Click the button below to test if the AI connection is working properly.
        </p>

        {/* Message */}
        {message && (
          <div className={`mb-4 p-4 rounded-lg ${
            message.type === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'
          }`}>
            <div className="font-semibold">{message.text}</div>
            {message.details && message.type === 'success' && (
              <div className="mt-2 text-sm">
                <div>Provider: {message.details.provider}</div>
                <div>Model: {message.details.model}</div>
                <div>Response: {message.details.response}</div>
              </div>
            )}
          </div>
        )}

        <button
          onClick={testConnection}
          disabled={testing}
          className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
        >
          {testing ? 'Testing...' : 'Test AI Connection'}
        </button>
      </div>
    </div>
  );
}

// Tab 4: Performance Metrics
function PerformanceMetricsTab() {
  return <PerformanceMetricsCard />;
}

// ============== Main Admin Page ==============

type TabType = 'content' | 'crawler' | 'upload' | 'ai-config' | 'performance';

const tabs: { id: TabType; label: string; icon: string }[] = [
  { id: 'content', label: 'Content Status', icon: '📁' },
  { id: 'crawler', label: 'Crawler', icon: '🕷️' },
  { id: 'upload', label: 'File Upload', icon: '📤' },
  { id: 'performance', label: 'Performance', icon: '📊' },
  { id: 'ai-config', label: 'AI Config', icon: '🤖' },
];

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState<TabType>('content');

  const renderTabContent = () => {
    switch (activeTab) {
      case 'content':
        return <ContentStatusTab />;
      case 'crawler':
        return <CrawlerManagementSection />;
      case 'upload':
        return <FileUploadTab />;
      case 'performance':
        return <PerformanceMetricsTab />;
      case 'ai-config':
        return <AIConfigTab />;
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-4 md:p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl md:text-4xl font-bold text-gray-800">Admin Console</h1>
          <p className="text-gray-800 mt-2">Unified management for crawler, content, and AI configuration</p>
        </div>

        {/* Tabs */}
        <div className="bg-white rounded-xl shadow-lg overflow-hidden">
          {/* Tab Navigation */}
          <div className="border-b border-gray-200 overflow-x-auto">
            <nav className="flex min-w-max">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-4 md:px-6 py-4 text-sm font-medium whitespace-nowrap transition-colors ${
                    activeTab === tab.id
                      ? 'border-b-2 border-blue-600 text-blue-600 bg-blue-50'
                      : 'text-gray-800 hover:text-gray-900 hover:bg-gray-50'
                  }`}
                >
                  <span className="text-lg">{tab.icon}</span>
                  <span>{tab.label}</span>
                </button>
              ))}
            </nav>
          </div>

          {/* Tab Content */}
          <div className="p-4 md:p-6">
            {renderTabContent()}
          </div>
        </div>

        {/* Quick Links */}
        <div className="mt-6 flex flex-wrap gap-4 justify-center">
          <a
            href="/"
            className="px-4 py-2 bg-white text-gray-800 rounded-lg shadow hover:bg-gray-50 transition"
          >
            ← Back to Chat
          </a>
        </div>
      </div>
    </div>
  );
}
