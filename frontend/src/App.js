import React, { useState, useEffect, useRef } from 'react';
import teethSvgPaths from './teethSvgPaths';
import axios from 'axios';
import './index.css';

const API_BASE = process.env.NODE_ENV === 'production' ? '' : 'http://localhost:8000';

// Session Management Class
class SessionManager {
  constructor() {
    this.sessionId = localStorage.getItem('segmentation_session_id');
  }

  async getSessionId() {
    if (!this.sessionId) {
      try {
        const response = await axios.post(`${API_BASE}/api/session`);
        this.sessionId = response.data.session_id;
        localStorage.setItem('segmentation_session_id', this.sessionId);
        console.log('Created new session:', this.sessionId);
      } catch (error) {
        console.error('Failed to create session:', error);
        throw error;
      }
    }
    return this.sessionId;
  }

  async createNewSession() {
    try {
      const response = await axios.post(`${API_BASE}/api/session`);
      this.sessionId = response.data.session_id;
      localStorage.setItem('segmentation_session_id', this.sessionId);
      console.log('Created new session for upload:', this.sessionId);
      return this.sessionId;
    } catch (error) {
      console.error('Failed to create new session:', error);
      throw error;
    }
  }

  getHeaders() {
    const headers = {'ngrok-skip-browser-warning': 'true'};
    if (this.sessionId) {
      headers['X-Session-ID'] = this.sessionId;
    }
    return headers;
  }

  async apiCall(url, config = {}) {
    await this.getSessionId();
    const headers = { ...this.getHeaders(), ...config.headers };
    
    try {
      return await axios({ ...config, url, headers });
    } catch (error) {
      // If session not found, clear it and retry once with a new session
      if (error.response?.status === 404 && error.response?.data?.detail?.includes('Session not found')) {
        console.warn('Session expired, creating new session');
        this.clearSession();
        await this.getSessionId(); // Create new session
        const newHeaders = { ...this.getHeaders(), ...config.headers };
        return axios({ ...config, url, headers: newHeaders });
      }
      throw error;
    }
  }

  clearSession() {
    this.sessionId = null;
    localStorage.removeItem('segmentation_session_id');
  }

  getCurrentSessionId() {
    return this.sessionId;
  }
}

function App() {
  const teethPositions = [
  // Coordinates refined for a smoother, more symmetrical overlay on the dental chart.
  // The origin (x:0, y:0) corresponds to the top-left of the container.

  // Upper Arch (Teeth 1-16, Patient's Upper Right to Upper Left)
  { id: 1, x: 85.74, y: 74.31 },   { id: 2, x: 84.95, y: 63.2 },   { id: 3, x: 84.35, y: 51.32 },   { id: 4, x: 81.97, y: 41.36 }, 
  { id: 5, x: 79.79, y: 32.93 },   { id: 6, x: 78.2, y: 25.27 },   { id: 7, x: 74.43, y: 17.61 },   { id: 8, x: 68.88, y: 12.62 }, 
  { id: 9, x: 62.33, y: 11.86 },   { id: 10, x: 57.17, y: 19.14 },   { id: 11, x: 53.4, y: 25.27 },   { id: 12, x: 51.81, y: 32.93 }, 
  { id: 13, x: 48.84, y: 40.98 },   { id: 14, x: 47.25, y: 51.7 },   { id: 15, x: 46.06, y: 61.67 },   { id: 16, x: 45.66, y: 72.78 }, 

  // Lower Arch (Teeth 17-32, Patient's Lower Left to Lower Right)
  { id: 17, x: -4.93, y: 66.65 },   { id: 18, x: -3.54, y: 53.24 },   { id: 19, x: -2.55, y: 41.36 },   { id: 20, x: -0.17, y: 31.78 }, 
  { id: 21, x: 2.81, y: 23.74 },   { id: 22, x: 6.38, y: 19.14 },   { id: 23, x: 9.75, y: 16.07 },   { id: 24, x: 13.12, y: 13.01 }, 
  { id: 25, x: 16.5, y: 13.39 },   { id: 26, x: 20.27, y: 14.92 },   { id: 27, x: 24.04, y: 18.37 },   { id: 28, x: 27.41, y: 23.35 }, 
  { id: 29, x: 30.19, y: 31.4 },   { id: 30, x: 32.57, y: 41.36 },   { id: 31, x: 33.36, y: 53.24 },   { id: 32, x: 34.75, y: 67.8 },

].map(p => ({ ...p, x: p.x + 10, y: p.y + 5 }));

  // State management
  const [file, setFile] = useState(null);
  const [fileInfo, setFileInfo] = useState(null);
  const [currentAxis, setCurrentAxis] = useState(2); // Start with axial
  const [currentSlice, setCurrentSlice] = useState(0);
  const [sliceData, setSliceData] = useState(null);
  const [markedPoints, setMarkedPoints] = useState([]);
  const [totalPoints, setTotalPoints] = useState(0);
  const [status, setStatus] = useState({ type: '', message: '' });
  const [loading, setLoading] = useState(false);
  const [segmentationFiles, setSegmentationFiles] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [selectedPointNumber, setSelectedPointNumber] = useState(null);
  const [allPoints, setAllPoints] = useState({}); // Store all points globally
  const [colorTemplate, setColorTemplate] = useState([]); // Store color template
  
  const canvasRef = useRef(null);
  const fileInputRef = useRef(null);
  const sessionManagerRef = useRef(new SessionManager());
  
  const axisNames = ['Sagittal', 'Coronal', 'Axial'];

  // Initialize session and restore state on component mount
  useEffect(() => {
    const initializeSession = async () => {
      try {
        const sessionId = await sessionManagerRef.current.getSessionId();
        setSessionId(sessionId);
        setStatus({ type: 'info', message: `Session initialized: ${sessionId.substring(0, 8)}... (Upload a file to begin)` });
        
        // Fetch color template
        await fetchColorTemplate();
        
        // Try to restore session state (but only if there's existing data)
        await restoreSessionState();
      } catch (error) {
        setStatus({ type: 'error', message: 'Failed to initialize session' });
      }
    };
    
    initializeSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Restore session state from backend
  const restoreSessionState = async () => {
    try {
      const response = await sessionManagerRef.current.apiCall(`${API_BASE}/api/status`, {
        method: 'GET'
      });
      
      const sessionData = response.data;
      console.log('Session data:', sessionData);
      
      // If file is already uploaded in this session
      if (sessionData.file_uploaded && sessionData.file_info) {
        setFileInfo(sessionData.file_info);
        setFile({ name: sessionData.file_info.filename || 'Uploaded file' }); // Create a mock file object
        setTotalPoints(sessionData.total_points || 0);
        
        // Restore current view state
        const restoredAxis = sessionData.current_axis !== undefined ? sessionData.current_axis : 2;
        const restoredSlice = sessionData.current_slice !== undefined ? sessionData.current_slice : 0;
        
        setCurrentAxis(restoredAxis);
        setCurrentSlice(restoredSlice);
        
        // Check if segmentation files exist
        if (sessionData.segmentation_files_exist) {
          setSegmentationFiles(true);
        }
        
        setStatus({ 
          type: 'success', 
          message: `Session restored: ${sessionData.file_info.filename || 'file'} loaded with ${sessionData.total_points || 0} points` 
        });
        
        // Load the current slice
        setTimeout(() => {
          loadSlice(restoredAxis, restoredSlice, sessionData.file_info);
        }, 100);
      }
    } catch (error) {
      if (error.response?.status === 404) {
        console.log('Session expired or not found, starting fresh');
        // Update session ID display
        const newSessionId = sessionManagerRef.current.getCurrentSessionId();
        setSessionId(newSessionId);
      } else {
        console.log('No previous session state to restore:', error.response?.status);
      }
      // This is normal for new sessions, don't show error
    }
  };
  
  // Upload file
  const handleFileUpload = async (selectedFile) => {
    if (!selectedFile) return;
    
    // Validate file type
    const isNifti = selectedFile.name.toLowerCase().endsWith('.nii') || selectedFile.name.toLowerCase().endsWith('.nii.gz');
    const isDicom = selectedFile.name.toLowerCase().endsWith('.dcm');
    const isDicomZip = selectedFile.name.toLowerCase().endsWith('.zip');
    if (!isNifti && !isDicom && !isDicomZip) {
      setStatus({ type: 'error', message: 'Invalid file type. Please upload .nii, .nii.gz, a DICOM .zip, or select any .dcm file in a DICOM series folder.' });
      return;
    }
    
    // Check file size (1000MB limit)
    const maxSize = 1000 * 1024 * 1024; // 1000MB
    if (selectedFile.size > maxSize) {
      setStatus({ type: 'error', message: `File too large (${(selectedFile.size / (1024*1024)).toFixed(1)}MB). Maximum size is 1000MB.` });
      return;
    }
    
    setLoading(true);
    
    try {
      // Create a new session for each file upload
      setStatus({ type: 'info', message: 'Creating new session for upload...' });
      const newSessionId = await sessionManagerRef.current.createNewSession();
      setSessionId(newSessionId);
      
      // Reset state for new session
      setFile(null);
      setFileInfo(null);
      setSliceData(null);
      setMarkedPoints([]);
      setTotalPoints(0);
      setSegmentationFiles(false);
      setCurrentAxis(2);
      setCurrentSlice(0);
      setSelectedPointNumber(null);
      setAllPoints({});
      
      // Fetch color template for new session
      await fetchColorTemplate();
      
      setStatus({ type: 'info', message: `Uploading ${selectedFile.name} (${(selectedFile.size / (1024*1024)).toFixed(1)}MB)...` });
      
      const formData = new FormData();
      // If DICOM file, collect all .dcm files in the folder and zip them
      if (isDicom && selectedFile.webkitRelativePath) {
        // User selected a folder, collect all .dcm files
        // This requires input type="file" with webkitdirectory attribute
        // For now, just upload the selected file
        formData.append('file', selectedFile);
      } else if (isDicom) {
        // Just upload the selected .dcm file
        formData.append('file', selectedFile);
      } else {
        formData.append('file', selectedFile);
      }

      const response = await sessionManagerRef.current.apiCall(`${API_BASE}/api/upload`, {
        method: 'POST',
        data: formData,
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 1200000, // 20 minute timeout for large files
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          setStatus({ type: 'info', message: `Uploading... ${percentCompleted}%` });
        }
      });
      
      setFile(selectedFile);
      setFileInfo(response.data);
      setCurrentSlice(0);
      setStatus({ 
        type: 'success', 
        message: `File uploaded successfully! Shape: ${response.data.shape?.join(' × ')} (New Session: ${newSessionId.substring(0, 8)}...)` 
      });
      
      console.log('Upload successful, calling loadSlice with:', { currentAxis, fileInfo: response.data });
      
      // Load initial slice - pass fileInfo directly to avoid state timing issues
      setTimeout(() => {
        console.log('setTimeout callback executing');
        loadSlice(2, 0, response.data); // Always start with axial view, slice 0
      }, 100);
      
    } catch (error) {
      console.error('Upload error:', error);
      let errorMessage = 'Failed to upload file';
      
      if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      } else if (error.code === 'ECONNABORTED') {
        errorMessage = 'Upload timeout. Please try with a smaller file.';
      } else if (error.message) {
        errorMessage = error.message;
      }
      
      setStatus({ type: 'error', message: errorMessage });
    } finally {
      setLoading(false);
    }
  };
  
  // Load slice data
  const loadSlice = async (axis, sliceIndex, providedFileInfo = null) => {
    const currentFileInfo = providedFileInfo || fileInfo;
    console.log('loadSlice called:', { axis, sliceIndex, fileInfo: currentFileInfo });
    if (!currentFileInfo) {
      console.log('No fileInfo available, skipping loadSlice');
      return;
    }

    try {
      console.log('Making API call to:', `${API_BASE}/api/slice/${axis}/${sliceIndex}`);
      const response = await sessionManagerRef.current.apiCall(`${API_BASE}/api/slice/${axis}/${sliceIndex}`, {
        method: 'GET'
      });
      console.log('Slice data received:', response.data);
      setSliceData(response.data);
      setMarkedPoints(response.data.marked_points || []);
      
      // Also fetch all points globally for the status table
      await fetchAllPoints();
      
      drawSlice(response.data.slice_data, response.data.marked_points || [], axis);
    } catch (error) {
      console.error('Error loading slice:', error);
      setStatus({ 
        type: 'error', 
        message: error.response?.data?.detail || 'Failed to load slice' 
      });
    }
  };

  // Fetch all points globally for status table
  const fetchAllPoints = async () => {
    try {
      const response = await sessionManagerRef.current.apiCall(`${API_BASE}/api/points`, {
        method: 'GET'
      });
      
      // Organize points by point number
      const pointsMap = {};
      if (response.data.points) {
        response.data.points.forEach(point => {
          pointsMap[point.point_number] = point;
        });
      }
      setAllPoints(pointsMap);
      
    } catch (error) {
      console.error('Error fetching all points:', error);
    }
  };
  
  // Fetch color template from backend
  const fetchColorTemplate = async () => {
    try {
      const response = await sessionManagerRef.current.apiCall(`${API_BASE}/api/color_template`, {
        method: 'GET'
      });
      
      setColorTemplate(response.data.color_template);
      
    } catch (error) {
      console.error('Error fetching color template:', error);
    }
  };
  
  // Draw slice on canvas
  const drawSlice = (data, points, axis = currentAxis) => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;

    const ctx = canvas.getContext('2d');
    const height = data.length;
    const width = data[0].length;

    // Set canvas size
    canvas.width = width;
    canvas.height = height;

    // Create image data
    const imageData = ctx.createImageData(width, height);

    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const value = data[y][x];
        const index = (y * width + x) * 4;
        imageData.data[index] = value;     // R
        imageData.data[index + 1] = value; // G
        imageData.data[index + 2] = value; // B
        imageData.data[index + 3] = 255;   // A
      }
    }

    ctx.putImageData(imageData, 0, 0);

    // --- START: Added code for orientation labels ---
    const orientationLabels = {
      // Labels for [Top, Bottom, Left, Right]
      0: ['A', 'P', 'R', 'L'], // Sagittal view (S->R, I->L)
      1: ['R', 'L', 'S', 'I'], // Coronal view
      2: ['R', 'L', 'A', 'P']  // Axial view (as in the reference image)
    };

    const currentLabels = orientationLabels[axis];
    if (!currentLabels) return; // Do not draw if axis is unknown

    ctx.fillStyle = '#00FFFF'; // Bright cyan, similar to reference crosshairs
    ctx.font = 'bold 18px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const margin = 10; // Distance from canvas edge

    // Draw labels
    ctx.fillText(currentLabels[0], width / 2, margin);        // Top
    ctx.fillText(currentLabels[1], width / 2, height - margin); // Bottom
    ctx.fillText(currentLabels[2], margin, height / 2);        // Left
    ctx.fillText(currentLabels[3], width - margin, height / 2); // Right
    // --- END: Added code for orientation labels ---

    // Draw points
    points.forEach((point, index) => {
      // Use color from backend if available, otherwise default red
      let pointColor = '#ff0000';
      if (point.color) {
        pointColor = `rgb(${point.color.r}, ${point.color.g}, ${point.color.b})`;
      }

      ctx.fillStyle = pointColor;
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1;

      ctx.beginPath();
      ctx.arc(point.x, point.y, 3, 0, 2 * Math.PI);
      ctx.fill();
      ctx.stroke();

      // Draw point number with contrasting color
      ctx.fillStyle = '#000000';
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1;
      ctx.font = 'bold 12px Arial';
      const text = String(point.point_number || index + 1);
      ctx.strokeText(text, point.x + 6, point.y - 6);
      ctx.fillText(text, point.x + 6, point.y - 6);
    });
  };
  
  // Handle canvas click to mark points
  const handleCanvasClick = async (event) => {
    if (!sliceData) return;
    
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    
    const x = Math.round((event.clientX - rect.left) * scaleX);
    const y = Math.round((event.clientY - rect.top) * scaleY);
    
    try {
      const requestData = {
        axis: currentAxis,
        slice_index: currentSlice,
        point: { x, y }
      };
      
      // If a specific point number is selected, include it
      if (selectedPointNumber !== null) {
        requestData.point_number = selectedPointNumber;
      }
      
      const response = await sessionManagerRef.current.apiCall(`${API_BASE}/api/mark_point`, {
        method: 'POST',
        data: requestData
      });
      
      setTotalPoints(response.data.total_points);
      setStatus({ 
        type: 'success', 
        message: `Point ${response.data.point_number} marked successfully (Session: ${response.data.session_id?.substring(0, 8)}...)` 
      });
      
      // Clear selection after marking
      setSelectedPointNumber(null);
      
      // Reload slice to show updated points
      loadSlice(currentAxis, currentSlice);
      
    } catch (error) {
      setStatus({ 
        type: 'error', 
        message: error.response?.data?.detail || 'Failed to mark point' 
      });
    }
  };

  // Remove a specific point
  const removePoint = async (pointNumber) => {
    try {
      const response = await sessionManagerRef.current.apiCall(`${API_BASE}/api/remove_point/${pointNumber}`, {
        method: 'DELETE'
      });
      
      setTotalPoints(response.data.total_points);
      setStatus({ 
        type: 'success', 
        message: `Point ${pointNumber} removed successfully` 
      });
      
      // Reload slice to show updated points
      loadSlice(currentAxis, currentSlice);
      
    } catch (error) {
      setStatus({ 
        type: 'error', 
        message: error.response?.data?.detail || 'Failed to remove point' 
      });
    }
  };

  // Select a point number for marking
  const selectPointForMarking = (pointNumber) => {
    setSelectedPointNumber(pointNumber);
    setStatus({ 
      type: 'info', 
      message: `Point ${pointNumber} selected for marking. Click on the image to place it.` 
    });
  };
  
  // Navigation functions
  const changeSlice = (direction) => {
    if (!sliceData) return;
    
    const newSlice = currentSlice + direction;
    if (newSlice >= 0 && newSlice < sliceData.max_slices) {
      setCurrentSlice(newSlice);
      loadSlice(currentAxis, newSlice);
    }
  };
  
  const changeAxis = (newAxis) => {
    setCurrentAxis(newAxis);
    setCurrentSlice(0);
    loadSlice(newAxis, 0);
  };
  
  // Clear all points
  const clearPoints = async () => {
    try {
      const response = await sessionManagerRef.current.apiCall(`${API_BASE}/api/points`, {
        method: 'DELETE'
      });
      setTotalPoints(0);
      setMarkedPoints([]);
      setAllPoints({});
      setSelectedPointNumber(null);
      setStatus({ 
        type: 'success', 
        message: `All points cleared (Session: ${response.data.session_id?.substring(0, 8)}...)` 
      });
      loadSlice(currentAxis, currentSlice);
    } catch (error) {
      setStatus({ 
        type: 'error', 
        message: error.response?.data?.detail || 'Failed to clear points' 
      });
    }
  };
  
  // Run segmentation
  const runSegmentation = async () => {
    if (totalPoints === 0) {
      setStatus({ type: 'error', message: 'No points marked for segmentation' });
      return;
    }
    
    setLoading(true);
    setSegmentationFiles(false); // Disable download button during processing
    setStatus({ type: 'info', message: 'Running segmentation... This may take a few minutes.' });
    
    try {
      const response = await sessionManagerRef.current.apiCall(`${API_BASE}/api/run_segmentation`, {
        method: 'POST'
      });
      
      if (response.data.status === 'success') {
        setSegmentationFiles(true);
        setStatus({ 
          type: 'success', 
          message: 'Segmentation complete! Ready to download.' 
        });
      } else {
        setStatus({ 
          type: 'error', 
          message: response.data.message 
        });
      }
    } catch (error) {
      setStatus({ 
        type: 'error', 
        message: error.response?.data?.detail || 'Segmentation failed' 
      });
    } finally {
      setLoading(false);
    }
  };
  
  // Download files
  const downloadFile = async (fileType) => {
    try {
      const headers = sessionManagerRef.current.getHeaders();
      const response = await axios.get(`${API_BASE}/api/download/${fileType}`, {
        headers,
        responseType: 'blob'
      });
      
      // Create download link
      const blob = new Blob([response.data]);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      
      // Extract filename from response headers or use default
      const contentDisposition = response.headers['content-disposition'];
      let filename = `segmentation_${fileType}.${fileType === 'segmentation' ? 'nii.gz' : 'txt'}`;
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="?(.+)"?/);
        if (filenameMatch) {
          filename = filenameMatch[1];
        }
      }
      
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      
      setStatus({ type: 'success', message: `Downloaded ${filename}` });
    } catch (error) {
      setStatus({ 
        type: 'error', 
        message: error.response?.data?.detail || `Failed to download ${fileType}` 
      });
    }
  };

  // Session management functions
  const createNewSession = async () => {
    try {
      sessionManagerRef.current.clearSession();
      const newSessionId = await sessionManagerRef.current.getSessionId();
      setSessionId(newSessionId);
      
      // Reset state for new session
      setFile(null);
      setFileInfo(null);
      setSliceData(null);
      setMarkedPoints([]);
      setTotalPoints(0);
      setSegmentationFiles(false);
      setSelectedPointNumber(null);
      setAllPoints({});
      
      // Fetch color template for new session
      await fetchColorTemplate();
      
      setStatus({ 
        type: 'success', 
        message: `New session created: ${newSessionId.substring(0, 8)}...` 
      });
    } catch (error) {
      setStatus({ type: 'error', message: 'Failed to create new session' });
    }
  };

  
  
  // Drag and drop handlers
  const handleDragOver = (e) => {
    e.preventDefault();
    e.currentTarget.classList.add('dragover');
  };
  
  const handleDragLeave = (e) => {
    e.preventDefault();
    e.currentTarget.classList.remove('dragover');
  };
  
  const handleDrop = (e) => {
    e.preventDefault();
    e.currentTarget.classList.remove('dragover');
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileUpload(files[0]);
    }
  };
  
  // Keyboard navigation
  useEffect(() => {
    const handleKeyPress = (e) => {
      if (!sliceData) return;
      
      switch (e.key) {
        case 'a':
        case 'A':
        case 'ArrowLeft':
          changeSlice(-1);
          break;
        case 'd':
        case 'D':
        case 'ArrowRight':
          changeSlice(1);
          break;
        case 'w':
        case 'W':
        case 'ArrowUp':
          changeAxis((currentAxis + 1) % 3);
          break;
        case 's':
        case 'S':
        case 'ArrowDown':
          changeAxis((currentAxis + 2) % 3);
          break;
        default:
          break;
      }
    };
    
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentAxis, currentSlice, sliceData]);
  
  return (
    <div className="app">
      <header className="header">
        <div className="header-content">
          <div className="header-text">
            <h1>Interactive 3D Teeth Segmentation</h1>
            <p>Upload a NIfTI file, mark teeth points, and generate segmentation</p>
          </div>
          <div className="session-info">
            <button 
              className="btn btn-primary"
              onClick={createNewSession}
              title="Create new session"
            >
              <span role="img" aria-label="new-session-icon" style={{ marginRight: '8px' }}>🔄</span>
              New Session
            </button>
          </div>
        </div>
      </header>
      
      {status.message && (
        <div className={`status-message status-${status.type}`}>
          {status.message}
        </div>
      )}
      
      <div className="main-content">
        <div className="viewer-section">
          {!file ? (
            <div 
              className="upload-area"
            >
              <h3>Upload NIfTI or DICOM Series</h3>
              <p>Drag and drop a .nii, .nii.gz, DICOM .zip, or any .dcm file from a DICOM series folder here, or click to browse</p>
              <p style={{ fontSize: '12px', color: '#666', marginTop: '10px' }}>
                🔄 Each upload creates a fresh session with clean state<br />
                <b>DICOM series:</b> Select any .dcm file in the folder containing the series.<br />
                <b>Advanced:</b> You can also upload a zipped folder of DICOM files.
              </p>
              {/* File upload for NIfTI, DICOM single file, or zip */}
              <input
                ref={fileInputRef}
                type="file"
                accept=".nii,.nii.gz,.dcm,.zip"
                style={{ display: 'none' }}
                onChange={e => {
                  if (e.target.files.length === 1) {
                    handleFileUpload(e.target.files[0]);
                  }
                }}
              />
              {/* Folder upload for DICOM series */}
              <input
                type="file"
                style={{ display: 'none' }}
                id="dicom-folder-input"
                webkitdirectory="true"
                multiple
                onChange={async (e) => {
                  const files = Array.from(e.target.files);
                  const dicomFiles = files.filter(f => f.name.toLowerCase().endsWith('.dcm'));
                  if (dicomFiles.length > 1) {
                    const JSZip = (await import('jszip')).default;
                    const zip = new JSZip();
                    dicomFiles.forEach(f => zip.file(f.name, f));
                    zip.generateAsync({ type: 'blob' }).then(blob => {
                      const zippedFile = new File([blob], 'dicom_series.zip', { type: 'application/zip' });
                      handleFileUpload(zippedFile);
                    });
                  } else if (dicomFiles.length === 1) {
                    handleFileUpload(dicomFiles[0]);
                  }
                }}
              />
              <div style={{ marginTop: '10px' }}>
                <button
                  className="btn btn-secondary"
                  onClick={() => fileInputRef.current?.click()}
                  style={{ marginRight: '10px' }}
                >
                  Upload File (.nii, .nii.gz, .dcm, .zip)
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={() => document.getElementById('dicom-folder-input').click()}
                >
                  Upload DICOM Folder
                </button>
              </div>
            </div>
          ) : (
            <div className="slice-viewer">
              <canvas
                ref={canvasRef}
                className="slice-canvas"
                onClick={handleCanvasClick}
                style={{ 
                  maxWidth: '100%', 
                  height: 'auto',
                  imageRendering: 'pixelated'
                }}
              />
            </div>
          )}
          
          {/* Point Status Map */}
          {sliceData && (
            <div className="point-status-map" style={{
              background: '#fff',
              borderRadius: '20px',
              boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
              padding: '32px 32px 24px 32px',
              width: '760px',
              minHeight: '480px',
              margin: '32px auto',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <h3>Point Status</h3>
              <p style={{ fontSize: '12px', color: '#666', marginBottom: '10px' }}>
                Select a tooth to mark it, or click a marked tooth to remove it.
              </p>
              <div className="teeth-map-container" style={{ width: '600px', height: '336px', display: 'flex', justifyContent: 'center', alignItems: 'center', margin: '0 auto' }}>
                <div
                  className="teeth-map"
                  style={{
                    position: 'relative',
                    width: '600px',
                    height: '336px', // 252/450*600 = 336 to maintain aspect ratio
                    backgroundImage: 'url(/teeth_map.png)',
                    backgroundSize: 'contain',
                    backgroundRepeat: 'no-repeat',
                    margin: '0 auto',
                  }}
                >
                  {/* Inline SVG for teeth map, each path is a clickable tooth */}
                  <svg
                    viewBox="0 0 640 268.8"
                    width="600"
                    height="336"
                    style={{ position: 'absolute', left: 0, top: 0, width: '600px', height: '336px', pointerEvents: 'none' }}
                  >
                    {/* Background paths for visual reference, not interactive */}
                    
                    <g id="teeth-bg">
                      {/* Optionally, add a faded background or outline here if needed */}
                    </g>
                  </svg>
                  <svg
                    viewBox="0 0 640 268.8"
                    width="600"
                    height="336"
                    style={{ position: 'absolute', left: 0, top: 0, width: '600px', height: '336px', pointerEvents: 'auto' }}
                  >
                    {teethSvgPaths.map(({ id, d }) => {
                      const pointNum = id;
                      const isMarked = allPoints[pointNum] !== undefined;
                      const isSelected = selectedPointNumber === pointNum;
                      let pointColor = 'rgba(255,255,255,0.7)';
                      if (colorTemplate.length > 0 && pointNum <= colorTemplate.length) {
                        const templateColor = colorTemplate[pointNum - 1];
                        pointColor = `rgb(${templateColor.r},${templateColor.g},${templateColor.b})`;
                      }
                      if (isMarked && allPoints[pointNum].color) {
                        pointColor = `rgb(${allPoints[pointNum].color.r},${allPoints[pointNum].color.g},${allPoints[pointNum].color.b})`;
                      }
                      // Add neumorphic shadow to unselected, unmarked teeth
                      const neumorphStyle = !isMarked && !isSelected ? {
                        filter: 'drop-shadow(2px 2px 3px rgba(255,220,220,0.5)) drop-shadow(-2px -2px 3px rgba(255,255,255,0.5))',
                        // Note: SVG does not support box-shadow, so use filter: drop-shadow for similar effect
                      } : {};
                      return (
                        <path
                          key={pointNum}
                          d={d}
                          fill={isMarked ? pointColor : (isSelected ? '#ffe066' : 'rgba(255,255,255,0.7)')}
                          stroke={isSelected ? '#007bff' : (isMarked ? '#333' : '#bbb')}
                          strokeWidth={isSelected ? 2 : 1}
                          style={{ cursor: 'pointer', transition: 'fill 0.2s, stroke 0.2s', ...neumorphStyle }}
                          onClick={e => {
                            e.stopPropagation();
                            if (isMarked) {
                              removePoint(pointNum);
                            } else {
                              selectPointForMarking(pointNum);
                            }
                          }}
                          title={`Tooth ${pointNum}`}
                        />
                      );
                    })}
                    {/* Statically add tooth number 1 at x=1, y=1. */}
                    <text x="607.5863"  y="231.80513" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text1">1</text>
                    <text x="604.54694" y="194.64091" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text2">2</text>   
                    <text x="597.67224" y="158.97824" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text3">3</text>    
                    <text x="582.63373" y="124.17489" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text4">4</text>    
                    <text x="568.45465" y="95.816612" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text5">5</text>    
                    <text x="555.56445" y="70.466026" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text6">6</text>    
                    <text x="534.51062" y="46.404461" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text7">7</text>    
                    <text x="497.98856" y="32.654987" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text8">8</text>    
                    <text x="460.17755" y="34.803345" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text9">9</text>    
                    <text x="420.6478"  y="49.841824" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text10">10</text>    
                    <text x="403.02362" y="71.325371" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text11">11</text>    
                    <text x="388.41479" y="94.246284" fontSize="14" fill="#777777" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text12">12</text>    
                    <text x="372.095"   y="124.60457" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text13">13</text>    
                    <text x="356.19717" y="158.97823" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text14">14</text>    
                    <text x="349.75214" y="193.3519"  fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text15">15</text>    
                    <text x="346.31473" y="230.73328" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text16">16</text>    
                    <text x="269.40366" y="223.85854" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text17">17</text>    
                    <text x="263.38828" y="175.30574" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text18">18</text>    
                    <text x="258.23221" y="127.18259" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text19">19</text>    
                    <text x="245.77176" y="93.668259" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text20">20</text>    
                    <text x="224.71788" y="64.45063"  fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text21">21</text>    
                    <text x="209.38269" y="43.826431" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text22">22</text>    
                    <text x="184.46179" y="26.209925" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text23">23</text>    
                    <text x="162.11121" y="20.194532" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text24">24</text>    
                    <text x="140.198"   y="20.194534" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text25">25</text>    
                    <text x="116.13641" y="27.92861"  fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text26">26</text>    
                    <text x="91.793518" y="44.256104" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text27">27</text>    
                    <text x="70.88031"  y="61.442936" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text28">28</text>    
                    <text x="46.685776" y="93.668259" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text29">29</text>    
                    <text x="35.654987" y="131.04964" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text30">30</text>    
                    <text x="27.920912" y="174.87605" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text31">31</text>    
                    <text x="24.483545" y="226.86623" fontSize="14" fill="#111111" strokeWidth="0.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="text32">32</text>

                    <text x="384" y="240" fontSize="18" fill="#111111" strokeWidth="1.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="textL1">L</text>
                    <text x="576" y="240" fontSize="18" fill="#111111" strokeWidth="1.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="textR1">R</text>
                    <text x="238" y="240" fontSize="18" fill="#111111" strokeWidth="1.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="textL2">L</text>
                    <text x="62" y="240" fontSize="18" fill="#111111" strokeWidth="1.8" textAnchor="middle" alignmentBaseline="middle" pointerEvents="none" id="textR2">R</text>
                    
                  </svg>
                </div>
              </div>
              {selectedPointNumber && (
                <div className="selected-point-info">
                  <p style={{ fontSize: '12px', color: '#007bff', marginTop: '10px' }}>
                    Point {selectedPointNumber} selected. Click on the 3D view to place it.
                  </p>
                  <button 
                    className="btn btn-sm btn-secondary"
                    onClick={() => setSelectedPointNumber(null)}
                    style={{ marginTop: '5px' }}
                  >
                    Cancel Selection
                  </button>
                </div>
              )}
            </div>
          )}
          
          {loading && (
            <div className="loading">
              <p>Processing...</p>
            </div>
          )}
        </div>
        
        <div className="controls-section">
          {fileInfo && (
            <div className="control-group">
              <h3>File Info</h3>
              <div className="info-display">
                <div>Shape: {fileInfo.shape?.join(' × ')}</div>
              </div>
            </div>
          )}
          
          {sliceData && (
            <>
              <div className="control-group">
                <h3>Current View</h3>
                <div className="info-display">
                  <div>Axis: {axisNames[currentAxis]}</div>
                  <div>Slice: {currentSlice + 1} / {sliceData.max_slices}</div>
                  <div>Points on slice: {markedPoints.length}</div>
                  <div>Total points: {totalPoints}</div>
                </div>
              </div>
              
              <div className="control-group">
                <h3>Navigation</h3>
                
                <div className="button-group">
                  {axisNames.map((name, index) => (
                    <button
                      key={index}
                      className={`btn ${currentAxis === index ? 'btn-primary' : 'btn-secondary'}`}
                      onClick={() => changeAxis(index)}
                    >
                      {name}
                    </button>
                  ))}
                </div>
                
                <div style={{ fontSize: '12px', color: '#666', marginTop: '10px' }}>
                  Keys: A/D or ←/→ = prev/next slice, W/S or ↑/↓ = change axis
                </div>
              </div>
              
              <div className="control-group">
                
                <button 
                  className="btn btn-danger"
                  onClick={clearPoints}
                  disabled={totalPoints === 0}
                  style={{ marginTop: '10px' }}
                >
                  Clear All Points
                </button>
              </div>
              
              <div className="control-group">
                <h3>Segmentation</h3>
                <button 
                  className="btn btn-success"
                  onClick={runSegmentation}
                  disabled={totalPoints === 0 || loading}
                  style={{ width: '100%', marginBottom: '10px' }}
                >
                  {loading ? (
                    <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                      <div className="progress-spinner"></div>
                      Processing...
                    </span>
                  ) : (
                    'Run Segmentation'
                  )}
                </button>
                
                {segmentationFiles && !loading && (
                  <button 
                    className="btn btn-primary"
                    onClick={() => downloadFile('segmentation')}
                    style={{ width: '100%' }}
                  >
                    Download NIfTI
                  </button>
                )}
                
                {loading && (
                  <div className="progress-container">
                    <div className="progress-bar">
                      <div className="progress-bar-fill"></div>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
          
          <div className="control-group">
            <h3>Instructions</h3>
            <div style={{ fontSize: '12px', color: '#666' }}>
              <p>1. Upload a NIfTI file (.nii or .nii.gz)</p>
              <p>   → Each upload creates a fresh session</p>
              <p>2. Navigate through slices and axes</p>
              <p>3. Click on teeth to mark points</p>
              <p>4. Run segmentation to generate results</p>
              <p>5. Download the segmented files</p>
              <p style={{ marginTop: '10px', fontStyle: 'italic' }}>
                💡 Fresh session = Clean slate for each file
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
