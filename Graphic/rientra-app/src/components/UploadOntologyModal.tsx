import { useState, useEffect, useRef } from 'react';
import { fetchStatus } from '../api/semanticService';
import './UploadOntologyModal.css';

interface UploadOntologyModalProps {
  onClose: () => void;
  onUploadSuccess: () => void;
}

type UploadState = 'idle' | 'copying' | 'restarting' | 'error';

export default function UploadOntologyModal({ onClose, onUploadSuccess }: UploadOntologyModalProps) {
  const [uploadState, setUploadState] = useState<UploadState>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const pollTimerRef = useRef<any>(null);
  const isComponentMounted = useRef(true);

  useEffect(() => {
    isComponentMounted.current = true;
    return () => {
      isComponentMounted.current = false;
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
      }
    };
  }, []);

  const handleSelectFile = async () => {
    const electronAPI = (window as any).electronAPI;
    if (!electronAPI?.showOpenDialog || !electronAPI?.uploadOntologyFile) {
      setErrorMessage('System functionality unavailable (Electron API not found).');
      setUploadState('error');
      return;
    }

    try {
      setErrorMessage(null);
      const dialogResult = await electronAPI.showOpenDialog({
        title: 'Select the ontology file',
        filters: [
          { name: 'Ontology Files (*.rdf, *.owl, *.ttl, *.n3)', extensions: ['rdf', 'owl', 'ttl', 'n3'] },
        ],
        properties: ['openFile'],
      });

      if (dialogResult.canceled || !dialogResult.filePaths?.length) {
        return;
      }

      const selectedPath = dialogResult.filePaths[0];
      setUploadState('copying');

      // Upload file via main process (copies and triggers python service stop/start)
      const res = await electronAPI.uploadOntologyFile(selectedPath);

      if (!res.ok) {
        throw new Error(res.error || 'Error while copying the file.');
      }

      // Enter restarting phase and poll python-service status
      setUploadState('restarting');
      startPolling();
    } catch (err: any) {
      console.error('[UploadOntologyModal] Error uploading file:', err);
      setErrorMessage(err.message || 'An unexpected error occurred.');
      setUploadState('error');
    }
  };

  const startPolling = () => {
    let attempt = 0;
    const maxAttempts = 40; // 20 seconds total

    const checkService = async () => {
      if (!isComponentMounted.current) return;
      attempt++;

      try {
        const statusResponse = await fetchStatus();
        
        // Once uvicorn is back up, it will either be "loading" (pellet reasoning started) or "ready".
        // Either status indicates the python service is alive and processing the new ontology.
        if (statusResponse.status === 'loading' || statusResponse.status === 'ready') {
          if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
          onUploadSuccess();
          return;
        }

        // If the service is running but returns error state (e.g. invalid file format), raise an error
        if (statusResponse.status === 'error') {
          throw new Error(statusResponse.message || 'The Python microservice encountered an error.');
        }
      } catch (err: any) {
        console.warn(`[UploadOntologyModal] Poll attempt ${attempt} failed:`, err.message);
        
        if (attempt >= maxAttempts) {
          if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
          setErrorMessage('Service restart timed out. Make sure the uploaded ontology is valid.');
          setUploadState('error');
          return;
        }
      }

      // Wait 500ms before checking again
      pollTimerRef.current = setTimeout(checkService, 500);
    };

    checkService();
  };

  return (
    <div className="uom-overlay">
      <div className="uom-container">
        <div className="uom-content">
          
          {uploadState === 'idle' && (
            <>
              <div className="uom-icon-wrapper" style={{ borderColor: 'rgba(239, 68, 68, 0.3)' }}>
                <svg className="uom-icon uom-icon-warning" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <h2 className="uom-title">Ontology Not Found</h2>
              <p className="uom-description">
                To proceed with the Decision Support System features, you need to upload an ontology file (e.g., <strong>.rdf</strong> or <strong>.owl</strong>) to initialize the knowledge base.
              </p>
              <div className="uom-info-box">
                The selected file will be copied into the service directory and the semantic reasoning engine will be configured automatically.
              </div>
              <div className="uom-actions">
                <button className="uom-btn-primary" onClick={handleSelectFile}>
                  <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                  </svg>
                  Select file from computer
                </button>
                <button className="uom-btn-secondary" onClick={onClose}>
                  Cancel
                </button>
              </div>
            </>
          )}

          {uploadState === 'copying' && (
            <div className="uom-loader-wrapper">
              <div className="uom-spinner">
                <div className="uom-spinner-inner" />
              </div>
              <div className="uom-status-text">Copying file...</div>
              <div className="uom-status-sub">Writing the ontology to the service folder...</div>
            </div>
          )}

          {uploadState === 'restarting' && (
            <div className="uom-loader-wrapper">
              <div className="uom-spinner">
                <div className="uom-spinner-inner" />
              </div>
              <div className="uom-status-text">Restarting semantic service...</div>
              <div className="uom-status-sub">Initializing Pellet reasoning engine...</div>
            </div>
          )}

          {uploadState === 'error' && (
            <>
              <div className="uom-icon-wrapper" style={{ borderColor: 'rgba(239, 68, 68, 0.3)' }}>
                <svg className="uom-icon uom-icon-warning" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h2 className="uom-title" style={{ color: '#fca5a5' }}>Upload Error</h2>
              <div className="uom-error-box">
                <strong>Error details:</strong>
                <span>{errorMessage || 'Unexpected error during initialization.'}</span>
              </div>
              <div className="uom-actions">
                <button className="uom-btn-primary" onClick={handleSelectFile}>
                  Retry upload
                </button>
                <button className="uom-btn-secondary" onClick={onClose}>
                  Back to Home
                </button>
              </div>
            </>
          )}

        </div>
      </div>
    </div>
  );
}
