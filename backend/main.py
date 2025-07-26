#!/usr/bin/env python3
"""
FastAPI Backend for Interactive 3D Teeth Segmentation Web Application

This backend provides APIs for:
- Loading NIfTI files
- Navigating slices 
- Managing marked points
- Running nnInteractive segmentation
- Downloading segmentation results
"""

import os
import json
import logging
import tempfile
import shutil
import uuid
import threading
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path

# Configure logging FIRST before any other imports that might log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

import uvicorn
import numpy as np
import nibabel as nib
import torch
from fastapi import FastAPI, HTTPException, UploadFile, File, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from huggingface_hub import snapshot_download

# DICOM support
import zipfile
import pydicom
from pydicom.errors import InvalidDicomError

# Try to import nnInteractive
try:
    from nnInteractive.inference.inference_session import nnInteractiveInferenceSession
    NNINTERACTIVE_AVAILABLE = True
except ImportError as e:
    NNINTERACTIVE_AVAILABLE = False
    logger.warning(f"nnInteractive not available: {e}")

# Log startup information
logger.info("=" * 60)
logger.info("TEETH SEGMENTATION API STARTING UP")
logger.info("=" * 60)
logger.info(f"nnInteractive availability: {NNINTERACTIVE_AVAILABLE}")
logger.info(f"PyTorch CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    logger.info(f"CUDA device count: {torch.cuda.device_count()}")
    logger.info(f"Current CUDA device: {torch.cuda.current_device()}")
    logger.info(f"CUDA device name: {torch.cuda.get_device_name()}")
logger.info("=" * 60)

# Pydantic models for API requests/responses
class Point2D(BaseModel):
    x: int
    y: int

class Point2DWithNumber(BaseModel):
    x: int
    y: int
    point_number: int
    color: Optional[Dict[str, int]] = None  # RGB color info

class Point3D(BaseModel):
    z: int
    y: int 
    x: int

class MarkPointRequest(BaseModel):
    axis: int
    slice_index: int
    point: Point2D
    point_number: Optional[int] = None  # Optional specific point number

class RunSegmentationRequest(BaseModel):
    points_3d: List[Point3D]

class SliceResponse(BaseModel):
    slice_data: List[List[int]]  # 2D array as nested lists
    axis: int
    slice_index: int
    max_slices: int
    marked_points: List[Point2DWithNumber]

class SegmentationStatus(BaseModel):
    status: str
    message: str
    file_path: Optional[str] = None
    unique_labels: Optional[List[int]] = None

class SessionInfo(BaseModel):
    session_id: str
    created_at: datetime
    last_activity: datetime
    nifti_loaded: bool
    nifti_shape: Optional[List[int]] = None
    total_points: int

# FastAPI app with increased limits for large NIfTI files
app = FastAPI(
    title="Interactive 3D Segmentation API", 
    version="1.0.0",
    # Increase default limits for large medical files
    openapi_url="/api/openapi.json"
)

# Enable CORS for frontend - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session-based state management
class SessionState:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.nifti_data: Optional[np.ndarray] = None
        self.nifti_affine: Optional[np.ndarray] = None
        self.nifti_header = None
        self.nifti_file_path: Optional[str] = None
        self.marked_points_2d: Dict[Tuple[int, int], List[Point2DWithNumber]] = {}
        self.all_3d_points: List[Point3D] = []
        self.point_counter: int = 0
        self.point_to_number: Dict[Tuple[int, int, int], int] = {}
        self.last_marked_number: int = 0  # Track the chronologically last marked point number
        self.session: Optional[object] = None
        self.output_files: List[str] = []
        
        # View state tracking
        self.current_axis: int = 2  # Default to axial view
        self.current_slice: int = 0  # Default to first slice
        
        # Color template for labels
        self.color_template = [
            {'idx': 1, 'r': 255, 'g': 0, 'b': 0, 'label': '#1'},
            {'idx': 2, 'r': 0, 'g': 255, 'b': 0, 'label': '#2'},
            {'idx': 3, 'r': 0, 'g': 0, 'b': 255, 'label': '#3'},
            {'idx': 4, 'r': 255, 'g': 255, 'b': 0, 'label': '#4'},
            {'idx': 5, 'r': 0, 'g': 255, 'b': 255, 'label': '#5'},
            {'idx': 6, 'r': 255, 'g': 0, 'b': 255, 'label': '#6'},
            {'idx': 7, 'r': 255, 'g': 239, 'b': 213, 'label': '#7'},
            {'idx': 8, 'r': 255, 'g': 170, 'b': 0, 'label': '#8'},
            {'idx': 9, 'r': 172, 'g': 0, 'b': 129, 'label': '#9'},
            {'idx': 10, 'r': 0, 'g': 166, 'b': 0, 'label': '#10'},
            {'idx': 11, 'r': 169, 'g': 102, 'b': 205, 'label': '#11'},
            {'idx': 12, 'r': 0, 'g': 0, 'b': 128, 'label': '#12'},
            {'idx': 13, 'r': 0, 'g': 203, 'b': 203, 'label': '#13'},
            {'idx': 14, 'r': 94, 'g': 117, 'b': 29, 'label': '#14'},
            {'idx': 15, 'r': 255, 'g': 43, 'b': 192, 'label': '#15'},
            {'idx': 16, 'r': 106, 'g': 90, 'b': 205, 'label': '#16'},
            {'idx': 17, 'r': 221, 'g': 166, 'b': 169, 'label': '#17'},
            {'idx': 18, 'r': 122, 'g': 202, 'b': 233, 'label': '#18'},
            {'idx': 19, 'r': 165, 'g': 91, 'b': 42, 'label': '#19'},
            {'idx': 20, 'r': 150, 'g': 185, 'b': 100, 'label': '#20'},
            {'idx': 21, 'r': 219, 'g': 112, 'b': 214, 'label': '#21'},
            {'idx': 22, 'r': 218, 'g': 217, 'b': 112, 'label': '#22'},
            {'idx': 23, 'r': 215, 'g': 64, 'b': 235, 'label': '#23'},
            {'idx': 24, 'r': 255, 'g': 182, 'b': 193, 'label': '#24'},
            {'idx': 25, 'r': 60, 'g': 179, 'b': 113, 'label': '#25'},
            {'idx': 26, 'r': 182, 'g': 158, 'b': 255, 'label': '#26'},
            {'idx': 27, 'r': 255, 'g': 228, 'b': 196, 'label': '#27'},
            {'idx': 28, 'r': 218, 'g': 165, 'b': 32, 'label': '#28'},
            {'idx': 29, 'r': 0, 'g': 128, 'b': 128, 'label': '#29'},
            {'idx': 30, 'r': 188, 'g': 143, 'b': 143, 'label': '#30'},
            {'idx': 31, 'r': 255, 'g': 105, 'b': 180, 'label': '#31'},
            {'idx': 32, 'r': 255, 'g': 218, 'b': 185, 'label': '#32'},
            {'idx': 33, 'r': 222, 'g': 184, 'b': 135, 'label': 'Bridge'},
            {'idx': 34, 'r': 127, 'g': 255, 'b': 0, 'label': 'Implant'},
        ]

    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.now()

    def clear_data(self):
        """Clear segmentation data but keep session alive"""
        self.nifti_data = None
        self.nifti_affine = None
        self.nifti_header = None
        if self.nifti_file_path and os.path.exists(self.nifti_file_path):
            try:
                os.remove(self.nifti_file_path)
            except:
                pass
        self.nifti_file_path = None
        self.marked_points_2d.clear()
        self.all_3d_points.clear()
        self.point_counter = 0
        self.point_to_number.clear()
        self.last_marked_number = 0  # Reset last marked number
        self.session = None
        
        # Reset view state
        self.current_axis = 2  # Default to axial view
        self.current_slice = 0  # Default to first slice
        
        # Clean up old output files
        for file_path in self.output_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
        self.output_files.clear()

    def get_point_color(self, point_number: int) -> Dict[str, int]:
        """Get RGB color for a point based on its number"""
        if point_number <= len(self.color_template):
            color = self.color_template[point_number - 1]
            return {'r': color['r'], 'g': color['g'], 'b': color['b']}
        else:
            # Default color for points beyond template
            return {'r': 255, 'g': 255, 'b': 255}

    def get_next_available_point_number(self) -> int:
        """Find the next point number (1 + last marked number chronologically)"""
        return self.last_marked_number + 1

class SessionManager:
    def __init__(self, session_timeout_hours: int = 24):
        self.sessions: Dict[str, SessionState] = {}
        self.session_timeout = timedelta(hours=session_timeout_hours)
        self.lock = threading.RLock()
        
        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_expired_sessions, daemon=True)
        self.cleanup_thread.start()
    
    def create_session(self) -> str:
        """Create a new session and return session ID"""
        with self.lock:
            session_id = str(uuid.uuid4())
            self.sessions[session_id] = SessionState(session_id)
            logger.info(f"Created new session: {session_id}")
            return session_id
    
    def get_session(self, session_id: str) -> SessionState:
        """Get session by ID, raise HTTPException if not found"""
        with self.lock:
            if session_id not in self.sessions:
                raise HTTPException(status_code=404, detail="Session not found")
            
            session = self.sessions[session_id]
            session.update_activity()
            return session
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        with self.lock:
            if session_id in self.sessions:
                session = self.sessions[session_id]
                session.clear_data()
                del self.sessions[session_id]
                logger.info(f"Deleted session: {session_id}")
                return True
            return False
    
    def get_all_sessions(self) -> List[SessionInfo]:
        """Get info about all active sessions"""
        with self.lock:
            return [
                SessionInfo(
                    session_id=session.session_id,
                    created_at=session.created_at,
                    last_activity=session.last_activity,
                    nifti_loaded=session.nifti_data is not None,
                    nifti_shape=list(session.nifti_data.shape) if session.nifti_data is not None else None,
                    total_points=len(session.all_3d_points)
                )
                for session in self.sessions.values()
            ]
    
    def _cleanup_expired_sessions(self):
        """Background thread to clean up expired sessions"""
        while True:
            try:
                current_time = datetime.now()
                expired_sessions = []
                
                with self.lock:
                    for session_id, session in self.sessions.items():
                        if current_time - session.last_activity > self.session_timeout:
                            expired_sessions.append(session_id)
                
                for session_id in expired_sessions:
                    self.delete_session(session_id)
                    logger.info(f"Cleaned up expired session: {session_id}")
                
                # Sleep for 1 hour before next cleanup
                time.sleep(3600)
                
            except Exception as e:
                logger.error(f"Error in session cleanup: {e}")
                time.sleep(3600)

# Global session manager
session_manager = SessionManager()

# Dependency to get session
def get_session_id(x_session_id: Optional[str] = Header(None)) -> str:
    """Get session ID from header, validate it exists"""
    if x_session_id is None:
        raise HTTPException(status_code=400, detail="Session ID header required")
    return x_session_id

def get_session(session_id: str = Depends(get_session_id)) -> SessionState:
    """Get session state"""
    try:
        return session_manager.get_session(session_id)
    except HTTPException as e:
        if e.status_code == 404:
            # Session expired or invalid, provide helpful error message
            raise HTTPException(
                status_code=404, 
                detail="Session not found or expired. Please refresh the page to create a new session."
            )
        raise

# Utility functions
def normalize_slice_for_display(slice_data: np.ndarray) -> np.ndarray:
    """Normalize slice data for display (0-255)"""
    if slice_data.max() > slice_data.min():
        normalized = ((slice_data - slice_data.min()) / 
                     (slice_data.max() - slice_data.min()) * 255).astype(np.uint8)
    else:
        normalized = np.zeros_like(slice_data, dtype=np.uint8)
    return normalized

def get_slice_data(session: SessionState, axis: int, slice_index: int) -> np.ndarray:
    """Extract slice data from 3D volume"""
    if session.nifti_data is None:
        raise HTTPException(status_code=400, detail="No NIfTI file loaded")
    
    if axis == 0:  # Sagittal
        return session.nifti_data[slice_index, :, :]
    elif axis == 1:  # Coronal
        return session.nifti_data[:, slice_index, :]
    else:  # axis == 2, Axial
        return session.nifti_data[:, :, slice_index]

def convert_2d_to_3d_coordinates(point_2d: Point2D, axis: int, slice_index: int) -> Point3D:
    """Convert 2D point to 3D coordinates"""
    if axis == 0:  # Sagittal
        return Point3D(z=slice_index, y=point_2d.y, x=point_2d.x)
    elif axis == 1:  # Coronal
        return Point3D(z=point_2d.y, y=slice_index, x=point_2d.x)
    else:  # axis == 2, Axial
        return Point3D(z=point_2d.y, y=point_2d.x, x=slice_index)

# API Routes

@app.post("/api/session")
async def create_new_session():
    """Create a new session"""
    session_id = session_manager.create_session()
    return {"session_id": session_id}

@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session"""
    success = session_manager.delete_session(session_id)
    if success:
        return {"message": "Session deleted successfully"}
    else:
        raise HTTPException(status_code=404, detail="Session not found")

@app.get("/api/sessions")
async def list_sessions():
    """List all active sessions"""
    return {"sessions": session_manager.get_all_sessions()}

@app.post("/api/upload")
async def upload_nifti(file: UploadFile = File(...), session: SessionState = Depends(get_session)):
    """Upload and load a NIfTI file with fresh session state"""

    try:
        file_ext = file.filename.lower().split('.')[-1]
        is_nifti = file.filename.lower().endswith(('.nii', '.nii.gz'))
        is_dicom_zip = file.filename.lower().endswith('.zip')
        is_dicom = file.filename.lower().endswith('.dcm')

        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        if file_size > 500 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large. Maximum size is 500MB.")

        logging.info(f"Uploading file: {file.filename} ({file_size / (1024*1024):.1f} MB) for session {session.session_id}")
        session.clear_data()
        session.update_activity()
        temp_dir = tempfile.mkdtemp()
        temp_file_path = os.path.join(temp_dir, file.filename)

        with open(temp_file_path, "wb") as buffer:
            while chunk := await file.read(8192):
                buffer.write(chunk)
        logging.info(f"File saved to: {temp_file_path}")

        if is_nifti:
            try:
                nii = nib.load(temp_file_path)
                session.nifti_data = nii.get_fdata()
                session.nifti_affine = nii.affine
                session.nifti_header = nii.header
                session.nifti_file_path = temp_file_path
                logger.info(f"Loaded NIfTI file: {file.filename} for session {session.session_id}")
                logger.info(f"Shape: {session.nifti_data.shape}")
                logger.info(f"Range: {session.nifti_data.min():.2f} to {session.nifti_data.max():.2f}")
                return {
                    "message": "File uploaded successfully",
                    "session_id": session.session_id,
                    "shape": list(session.nifti_data.shape),
                    "data_range": [float(session.nifti_data.min()), float(session.nifti_data.max())],
                    "file_type": "nifti"
                }
            except Exception as e:
                logger.error(f"Failed to load NIfTI file: {e}")
                raise HTTPException(status_code=400, detail=f"Failed to load NIfTI file: {str(e)}")

        elif is_dicom_zip:
            dicom_dir = os.path.join(temp_dir, "dicom_series")
            os.makedirs(dicom_dir, exist_ok=True)
            with zipfile.ZipFile(temp_file_path, 'r') as zip_ref:
                zip_ref.extractall(dicom_dir)
            dicom_files = [os.path.join(dicom_dir, f) for f in os.listdir(dicom_dir) if f.lower().endswith('.dcm')]
            if not dicom_files:
                raise HTTPException(status_code=400, detail="No DICOM files found in uploaded zip.")
            slices = []
            for f in dicom_files:
                try:
                    ds = pydicom.dcmread(f)
                    slices.append(ds)
                except Exception as e:
                    logger.warning(f"Invalid DICOM file {f}: {e}")
                    continue
            if not slices:
                raise HTTPException(status_code=400, detail="No valid DICOM slices found.")
            try:
                slices.sort(key=lambda s: int(getattr(s, 'InstanceNumber', 0)))
            except Exception:
                try:
                    slices.sort(key=lambda s: float(getattr(s, 'SliceLocation', 0.0)))
                except Exception:
                    pass
            img_shape = slices[0].pixel_array.shape
            volume = np.stack([s.pixel_array for s in slices], axis=0)
            if len(volume.shape) == 3:
                session.nifti_data = volume
            else:
                raise HTTPException(status_code=400, detail=f"Unexpected DICOM volume shape: {volume.shape}")
            session.nifti_affine = None
            session.nifti_header = None
            session.nifti_file_path = dicom_dir
            logger.info(f"DICOM series loaded: {len(slices)} slices, shape: {session.nifti_data.shape}")
            logger.info(f"DICOM pixel value range: {session.nifti_data.min()} to {session.nifti_data.max()}")
            return {
                "message": "DICOM series uploaded and loaded successfully",
                "session_id": session.session_id,
                "shape": list(session.nifti_data.shape),
                "data_range": [float(session.nifti_data.min()), float(session.nifti_data.max())],
                "file_type": "dicom"
            }

        elif is_dicom:
            dicom_file_path = temp_file_path
            dicom_dir = temp_dir
            if '/' in file.filename or '\\' in file.filename:
                subfolder = os.path.dirname(os.path.join(temp_dir, file.filename))
                if os.path.exists(subfolder):
                    dicom_dir = subfolder
            dicom_files = [os.path.join(dicom_dir, f) for f in os.listdir(dicom_dir) if f.lower().endswith('.dcm')]
            if not dicom_files:
                dicom_files = [dicom_file_path]
            slices = []
            for f in dicom_files:
                try:
                    ds = pydicom.dcmread(f)
                    slices.append(ds)
                except Exception as e:
                    logger.warning(f"Invalid DICOM file {f}: {e}")
                    continue
            if not slices:
                raise HTTPException(status_code=400, detail="No valid DICOM slices found.")
            try:
                slices.sort(key=lambda s: int(getattr(s, 'InstanceNumber', 0)))
            except Exception:
                try:
                    slices.sort(key=lambda s: float(getattr(s, 'SliceLocation', 0.0)))
                except Exception:
                    pass
            img_shape = slices[0].pixel_array.shape
            volume = np.stack([s.pixel_array for s in slices], axis=0)
            if len(volume.shape) == 3:
                session.nifti_data = volume
            else:
                raise HTTPException(status_code=400, detail=f"Unexpected DICOM volume shape: {volume.shape}")
            session.nifti_affine = None
            session.nifti_header = None
            session.nifti_file_path = dicom_dir
            logger.info(f"DICOM series loaded: {len(slices)} slices, shape: {session.nifti_data.shape}")
            logger.info(f"DICOM pixel value range: {session.nifti_data.min()} to {session.nifti_data.max()}")
            return {
                "message": "DICOM series uploaded and loaded successfully",
                "session_id": session.session_id,
                "shape": list(session.nifti_data.shape),
                "data_range": [float(session.nifti_data.min()), float(session.nifti_data.max())],
                "file_type": "dicom"
            }

        else:
            raise HTTPException(status_code=400, detail="Invalid file type. Please upload .nii, .nii.gz, a DICOM .zip, or any .dcm file from a DICOM series folder.")
    except Exception as e:
        logger.error(f"Failed to load file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load file: {str(e)}")

@app.get("/api/slice/{axis}/{slice_index}")
async def get_slice(axis: int, slice_index: int, session: SessionState = Depends(get_session)) -> SliceResponse:
    """Get slice data for display"""
    try:
        if session.nifti_data is None:
            raise HTTPException(status_code=400, detail="No NIfTI file loaded")
        
        # Validate parameters
        if axis not in [0, 1, 2]:
            raise HTTPException(status_code=400, detail="Axis must be 0, 1, or 2")
        
        max_slices = session.nifti_data.shape[axis]
        if slice_index < 0 or slice_index >= max_slices:
            raise HTTPException(status_code=400, detail=f"Slice index must be 0-{max_slices-1}")
        
        # Update current view state
        session.current_axis = axis
        session.current_slice = slice_index
        session.update_activity()
        
        # Get slice data
        slice_data = get_slice_data(session, axis, slice_index)
        normalized_slice = normalize_slice_for_display(slice_data)
        
        # Get marked points for this slice
        slice_key = (axis, slice_index)
        marked_points = session.marked_points_2d.get(slice_key, [])
        
        # Ensure all points have color information
        for point in marked_points:
            if point.color is None:
                point.color = session.get_point_color(point.point_number)
        
        return SliceResponse(
            slice_data=normalized_slice.tolist(),
            axis=axis,
            slice_index=slice_index,
            max_slices=max_slices,
            marked_points=marked_points
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get slice: {str(e)}")

@app.post("/api/mark_point")
async def mark_point(request: MarkPointRequest, session: SessionState = Depends(get_session)):
    """Mark a point on a slice"""
    try:
        if session.nifti_data is None:
            raise HTTPException(status_code=400, detail="No NIfTI file loaded")
        
        # Convert to 3D coordinates
        point_3d = convert_2d_to_3d_coordinates(request.point, request.axis, request.slice_index)
        point_3d_tuple = (point_3d.z, point_3d.y, point_3d.x)
        
        # Handle specific point number request
        if request.point_number is not None:
            point_number = request.point_number
            
            # Remove existing point with this number if it exists
            if point_number in session.point_to_number.values():
                # Find and remove the old point
                old_point_tuple = None
                for pt_tuple, pt_num in session.point_to_number.items():
                    if pt_num == point_number:
                        old_point_tuple = pt_tuple
                        break
                
                if old_point_tuple:
                    # Remove from point_to_number mapping
                    del session.point_to_number[old_point_tuple]
                    
                    # Remove from all_3d_points
                    session.all_3d_points = [p for p in session.all_3d_points 
                                            if (p.z, p.y, p.x) != old_point_tuple]
                    
                    # Remove from all slice markings
                    for slice_key in list(session.marked_points_2d.keys()):
                        session.marked_points_2d[slice_key] = [
                            p for p in session.marked_points_2d[slice_key] 
                            if p.point_number != point_number
                        ]
            
            # Add new point with specific number
            session.all_3d_points.append(point_3d)
            session.point_to_number[point_3d_tuple] = point_number
            
            # Update counter if necessary
            if point_number > session.point_counter:
                session.point_counter = point_number
                
        else:
            # Normal sequential point marking - find next available number
            if point_3d_tuple not in session.point_to_number:
                # New point - assign next available number
                next_number = session.get_next_available_point_number()
                session.all_3d_points.append(point_3d)
                session.point_to_number[point_3d_tuple] = next_number
                
                # Update counter to highest used number
                if next_number > session.point_counter:
                    session.point_counter = next_number
                
                logger.info(f"Point {next_number} marked: 2D({request.point.x}, {request.point.y}) -> 3D{point_3d_tuple} (Session: {session.session_id})")
            
            # Get the point number
            point_number = session.point_to_number[point_3d_tuple]
        
        # Add to slice points with number
        slice_key = (request.axis, request.slice_index)
        if slice_key not in session.marked_points_2d:
            session.marked_points_2d[slice_key] = []
        
        # Remove any existing point with same number on this slice
        session.marked_points_2d[slice_key] = [
            p for p in session.marked_points_2d[slice_key] 
            if p.point_number != point_number
        ]
        
        # Add the new point
        point_color = session.get_point_color(point_number)
        point_with_number = Point2DWithNumber(
            x=request.point.x, 
            y=request.point.y, 
            point_number=point_number,
            color=point_color
        )
        session.marked_points_2d[slice_key].append(point_with_number)
        
        # Update the last marked number to track chronological order
        session.last_marked_number = point_number
        
        return {
            "message": "Point marked successfully",
            "point_number": point_number,
            "total_points": len(session.all_3d_points),
            "session_id": session.session_id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to mark point: {str(e)}")

@app.delete("/api/points")
async def clear_points(session: SessionState = Depends(get_session)):
    """Clear all marked points"""
    session.marked_points_2d.clear()
    session.all_3d_points.clear()
    session.point_counter = 0
    session.point_to_number.clear()
    session.last_marked_number = 0  # Reset last marked number
    
    return {
        "message": "All points cleared",
        "session_id": session.session_id
    }

@app.get("/api/points")
async def get_points(session: SessionState = Depends(get_session)):
    """Get all marked points"""
    # Create a list of all points with their numbers and coordinates
    all_points_list = []
    for point_3d in session.all_3d_points:
        point_tuple = (point_3d.z, point_3d.y, point_3d.x)
        point_number = session.point_to_number.get(point_tuple)
        if point_number:
            point_color = session.get_point_color(point_number)
            all_points_list.append({
                "point_number": point_number,
                "coordinates": {"x": point_3d.x, "y": point_3d.y, "z": point_3d.z},
                "color": point_color
            })
    
    return {
        "points": all_points_list,
        "points_2d": {f"{k[0]}_{k[1]}": v for k, v in session.marked_points_2d.items()},
        "points_3d": session.all_3d_points,
        "total_points": len(session.all_3d_points),
        "session_id": session.session_id
    }

@app.delete("/api/remove_point/{point_number}")
async def remove_point(point_number: int, session: SessionState = Depends(get_session)):
    """Remove a specific point by its number"""
    try:
        # Find the point tuple with this number
        point_tuple_to_remove = None
        for pt_tuple, pt_num in session.point_to_number.items():
            if pt_num == point_number:
                point_tuple_to_remove = pt_tuple
                break
        
        if point_tuple_to_remove is None:
            raise HTTPException(status_code=404, detail=f"Point {point_number} not found")
        
        # Remove from point_to_number mapping
        del session.point_to_number[point_tuple_to_remove]
        
        # Remove from all_3d_points
        session.all_3d_points = [p for p in session.all_3d_points 
                                if (p.z, p.y, p.x) != point_tuple_to_remove]
        
        # Remove from all slice markings
        for slice_key in list(session.marked_points_2d.keys()):
            session.marked_points_2d[slice_key] = [
                p for p in session.marked_points_2d[slice_key] 
                if p.point_number != point_number
            ]
            # Remove empty slice entries
            if not session.marked_points_2d[slice_key]:
                del session.marked_points_2d[slice_key]
        
        logger.info(f"Point {point_number} removed (Session: {session.session_id})")
        
        return {
            "message": f"Point {point_number} removed successfully",
            "total_points": len(session.all_3d_points),
            "session_id": session.session_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove point: {str(e)}")

def initialize_nn_session(session: SessionState):
    """Initialize nnInteractive session"""
    if not NNINTERACTIVE_AVAILABLE:
        logger.info("nnInteractive not available - skipping initialization")
        return False
    
    try:
        if not torch.cuda.is_available():
            logger.error("CUDA not available. nnInteractive requires GPU.")
            return False
        
        logger.info(f"Initializing nnInteractive session for {session.session_id}...")
        logger.info(f"CUDA device count: {torch.cuda.device_count()}")
        logger.info(f"Current CUDA device: {torch.cuda.current_device()}")
        
        session.session = nnInteractiveInferenceSession(
            device=torch.device("cuda:0"),
            verbose=False
        )
        
        # Download model if needed
        model_dir = os.path.join(os.path.expanduser("~"), ".nninteractive_models")
        os.makedirs(model_dir, exist_ok=True)
        logger.info(f"Model directory: {model_dir}")
        
        logger.info("Downloading/checking nnInteractive model...")
        download_path = snapshot_download(
            repo_id="nnInteractive/nnInteractive",
            allow_patterns=["nnInteractive_v1.0/*"],
            local_dir=model_dir,
            local_dir_use_symlinks=False
        )
        
        model_path = os.path.join(download_path, "nnInteractive_v1.0")
        logger.info(f"Model path: {model_path}")
        
        logger.info("Initializing model from trained folder...")
        session.session.initialize_from_trained_model_folder(model_path)
        logger.info(f"nnInteractive session initialized successfully for {session.session_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize nnInteractive for session {session.session_id}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def run_mock_segmentation(session: SessionState):
    """Run mock segmentation for testing"""
    logger.info(f"Running mock segmentation with {len(session.all_3d_points)} points for session {session.session_id}...")
    logger.info(f"NIfTI data shape: {session.nifti_data.shape}")
    logger.info(f"NIfTI data range: {session.nifti_data.min():.2f} to {session.nifti_data.max():.2f}")
    
    # Initialize segmentation volume
    mock_segmentation = np.zeros_like(session.nifti_data, dtype=np.uint8)
    
    for point_3d in session.all_3d_points:
        # Use the actual point number as the label
        point_tuple = (point_3d.z, point_3d.y, point_3d.x)
        segment_label = session.point_to_number.get(point_tuple)
        z, y, x = point_3d.z, point_3d.y, point_3d.x
        logger.info(f"Processing point {segment_label}/{len(session.all_3d_points)}: ({z}, {y}, {x})")
        
        # Define region around point
        radius = 12
        z_min, z_max = max(0, z-radius), min(session.nifti_data.shape[0], z+radius)
        y_min, y_max = max(0, y-radius), min(session.nifti_data.shape[1], y+radius)
        x_min, x_max = max(0, x-radius), min(session.nifti_data.shape[2], x+radius)
        
        logger.info(f"  Region bounds: z[{z_min}:{z_max}], y[{y_min}:{y_max}], x[{x_min}:{x_max}]")
        
        # Extract region and create mask
        region = session.nifti_data[z_min:z_max, y_min:y_max, x_min:x_max]
        center_hu = session.nifti_data[z, y, x]
        threshold = max(300, center_hu * 0.7)
        
        logger.info(f"  Center HU value: {center_hu:.2f}, Threshold: {threshold:.2f}")
        
        tooth_mask = region > threshold
        existing_mask = mock_segmentation[z_min:z_max, y_min:y_max, x_min:x_max] == 0
        final_mask = tooth_mask & existing_mask
        
        voxels_above_threshold = np.sum(tooth_mask)
        voxels_available = np.sum(existing_mask)
        voxels_segmented = np.sum(final_mask)
        
        logger.info(f"  Voxels above threshold: {voxels_above_threshold}")
        logger.info(f"  Available voxels: {voxels_available}")
        logger.info(f"  Final segmented voxels: {voxels_segmented}")
        
        mock_segmentation[z_min:z_max, y_min:y_max, x_min:x_max][final_mask] = segment_label
    
    total_segmented = np.sum(mock_segmentation > 0)
    unique_labels = np.unique(mock_segmentation[mock_segmentation > 0])
    logger.info(f"Mock segmentation completed: {total_segmented} total voxels segmented, {len(unique_labels)} unique labels")
    
    return mock_segmentation

def create_label_file(session: SessionState, output_path: str, segmentation: np.ndarray):
    """Create ITK-SNAP compatible label file"""
    unique_labels = np.unique(segmentation)
    unique_labels = unique_labels[unique_labels > 0]
    
    label_file_path = output_path.replace('.nii.gz', '_labels.txt')
    
    with open(label_file_path, 'w') as f:
        f.write("################################################\n")
        f.write("# ITK-SnAP Label Description File\n")
        f.write("# Generated by Interactive 3D Segmentation Tool\n")
        f.write("################################################\n")
        f.write("# IDX   -R-  -G-  -B-  -A--  VIS MSH  LABEL\n")
        f.write("################################################\n")
        
        # Background
        f.write(f"    0     0    0    0        0  0  0    \"Clear Label\"\n")
        
        # Segments
        for label in sorted(unique_labels):
            if label <= len(session.color_template):
                color = session.color_template[label - 1]
                r, g, b = color['r'], color['g'], color['b']
                label_name = color['label']
            else:
                r, g, b = 255, 255, 255
                label_name = f"#{label}"
            
            f.write(f"  {label:3d}  {r:3d}  {g:3d}  {b:3d}        1  1  1    \"{label_name}\"\n")
    
    return label_file_path

@app.post("/api/run_segmentation")
async def run_segmentation(session: SessionState = Depends(get_session)) -> SegmentationStatus:
    """Run segmentation on marked points"""
    try:
        if not session.all_3d_points:
            raise HTTPException(status_code=400, detail="No points marked")
        
        if session.nifti_data is None:
            raise HTTPException(status_code=400, detail="No NIfTI file loaded")
        
        logger.info(f"Running segmentation with {len(session.all_3d_points)} points for session {session.session_id}...")
        logger.info(f"NNINTERACTIVE_AVAILABLE: {NNINTERACTIVE_AVAILABLE}")
        logger.info(f"CUDA available: {torch.cuda.is_available() if torch else False}")
        
        # Clear previous segmentation files to avoid confusion
        for file_path in session.output_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Removed old segmentation file: {file_path}")
            except Exception as e:
                logger.warning(f"Could not remove file {file_path}: {e}")
        session.output_files.clear()
        
        # Try nnInteractive first, fall back to mock
        segmentation = None
        method = "mock"
        
        logger.info(f"Checking if nnInteractive is available and can be initialized...")
        if NNINTERACTIVE_AVAILABLE and initialize_nn_session(session):
            logger.info(f"nnInteractive initialization successful, attempting segmentation...")
            try:
                method = "nnInteractive"
                # Prepare image data
                logger.info(f"Preparing image data for nnInteractive...")
                nifti_data = session.nifti_data.astype(np.float32)
                if nifti_data.ndim == 3:
                    image_4d = nifti_data[None]
                else:
                    image_4d = nifti_data
                logger.info(f"Image shape prepared: {image_4d.shape}")
                
                # Initialize segmentation
                combined_segmentation = np.zeros(image_4d.shape[1:], dtype=np.uint8)
                logger.info(f"Processing {len(session.all_3d_points)} points with nnInteractive...")
                
                # Process each point separately
                for point_3d in session.all_3d_points:
                    # Use the actual point number as the label
                    point_tuple = (point_3d.z, point_3d.y, point_3d.x)
                    segment_label = session.point_to_number.get(point_tuple)
                    logger.info(f"Processing point {segment_label}/{len(session.all_3d_points)}: {point_3d}")
                    
                    # Set image and target buffer
                    session.session.set_image(image_4d)
                    target_buffer = torch.zeros(image_4d.shape[1:], dtype=torch.uint8)
                    session.session.set_target_buffer(target_buffer)
                    
                    # Add point interaction
                    point_tuple = (point_3d.z, point_3d.y, point_3d.x)
                    session.session.add_point_interaction(point_tuple, include_interaction=True)
                    
                    # Get segmentation
                    point_segmentation = target_buffer.clone().cpu().numpy()
                    mask = point_segmentation > 0
                    available_mask = combined_segmentation == 0
                    final_mask = mask & available_mask
                    
                    voxels_segmented = np.sum(final_mask)
                    logger.info(f"Point {segment_label} segmented {voxels_segmented} voxels")
                    
                    combined_segmentation[final_mask] = segment_label
                
                segmentation = combined_segmentation
                logger.info(f"nnInteractive segmentation completed successfully")
                
            except Exception as e:
                logger.error(f"nnInteractive failed for session {session.session_id}: {e}, falling back to mock")
                method = "mock"
                segmentation = None
        else:
            logger.info(f"nnInteractive not available or initialization failed, using mock segmentation")
        
        # Fall back to mock segmentation
        if segmentation is None:
            logger.info(f"Starting mock segmentation...")
            segmentation = run_mock_segmentation(session)
        
        # Save results
        logger.info(f"Saving segmentation results...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = tempfile.mkdtemp()
        output_path = os.path.join(output_dir, f"segmented_{timestamp}_{session.session_id[:8]}.nii.gz")

        logger.info(f"Output directory: {output_dir}")
        logger.info(f"Output file path: {output_path}")

        # Only apply flipping/transposing for DICOM folder input (not NIfTI)
        seg_to_save = segmentation
        if session.nifti_file_path and isinstance(session.nifti_file_path, str) and os.path.isdir(session.nifti_file_path):
            # Transpose from (Z, Y, X) to (X, Y, Z)
            seg_to_save = np.transpose(seg_to_save, (2, 1, 0))
            # Flip along Z axis to make it right-side up (flip last axis)
            seg_to_save = np.flip(seg_to_save, axis=2)
            logger.info("Applied transpose and flip to segmentation output for DICOM folder upload.")

        # Create NIfTI image with same affine and header if available, else identity
        affine = session.nifti_affine if session.nifti_affine is not None else np.eye(4)
        header = session.nifti_header if session.nifti_header is not None else None
        segmentation_nii = nib.Nifti1Image(
            seg_to_save.astype(np.uint8),
            affine,
            header
        )
        nib.save(segmentation_nii, output_path)
        logger.info(f"Segmentation NIfTI file saved: {output_path}")
        
        # Create label file
        label_file_path = create_label_file(session, output_path, segmentation)
        logger.info(f"Label file created: {label_file_path}")
        
        # Store file paths for cleanup
        session.output_files.extend([output_path, label_file_path])
        
        # Get statistics
        unique_labels = np.unique(segmentation[segmentation > 0])
        
        logger.info(f"Segmentation complete for session {session.session_id}: {len(unique_labels)} segments created using {method}")
        logger.info(f"Unique labels: {unique_labels.tolist()}")
        logger.info(f"Files available for download: {len(session.output_files)}")
        
        return SegmentationStatus(
            status="success",
            message=f"Segmentation completed using {method}. {len(unique_labels)} segments created.",
            file_path=output_path,
            unique_labels=unique_labels.tolist()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        return SegmentationStatus(
            status="error",
            message=f"Segmentation failed: {str(e)}"
        )

@app.get("/api/download/{file_type}")
async def download_file(file_type: str, session: SessionState = Depends(get_session)):
    """Download segmentation files"""
    if not session.output_files:
        raise HTTPException(status_code=404, detail="No segmentation files available")
    
    if file_type == "segmentation":
        # Find the most recent .nii.gz file (last one added)
        nii_files = [f for f in session.output_files if f.endswith('.nii.gz')]
        if nii_files:
            latest_file = nii_files[-1]  # Get the last (most recent) file
            # Ensure proper filename with .nii.gz extension
            original_filename = os.path.basename(latest_file)
            if not original_filename.endswith('.nii.gz'):
                original_filename += '.nii.gz'
            
            return FileResponse(
                path=latest_file,
                media_type='application/octet-stream',
                filename=original_filename,
                headers={"Content-Disposition": f"attachment; filename=\"{original_filename}\""}
            )
    elif file_type == "labels":
        # Find the most recent .txt file (last one added) 
        txt_files = [f for f in session.output_files if f.endswith('.txt')]
        if txt_files:
            latest_file = txt_files[-1]  # Get the last (most recent) file
            # Ensure proper filename with .txt extension
            original_filename = os.path.basename(latest_file)
            if not original_filename.endswith('.txt'):
                original_filename += '.txt'
                
            return FileResponse(
                path=latest_file,
                media_type='text/plain',
                filename=original_filename,
                headers={"Content-Disposition": f"attachment; filename=\"{original_filename}\""}
            )
    
    raise HTTPException(status_code=404, detail=f"File type '{file_type}' not found")

@app.get("/api/status")
async def get_status(session: SessionState = Depends(get_session)):
    """Get application status and session state"""
    # Get file info if available
    file_info = None
    if session.nifti_data is not None:
        file_info = {
            "filename": os.path.basename(session.nifti_file_path) if session.nifti_file_path else "uploaded_file.nii.gz",
            "shape": list(session.nifti_data.shape),
            "data_range": [float(session.nifti_data.min()), float(session.nifti_data.max())]
        }
    
    # Check if segmentation files exist
    segmentation_files_exist = len(session.output_files) > 0
    
    return {
        "session_id": session.session_id,
        "file_uploaded": session.nifti_data is not None,
        "file_info": file_info,
        "total_points": len(session.all_3d_points),
        "current_axis": session.current_axis,
        "current_slice": session.current_slice,
        "segmentation_files_exist": segmentation_files_exist,
        "nninteractive_available": NNINTERACTIVE_AVAILABLE,
        "cuda_available": torch.cuda.is_available() if torch else False,
        "created_at": session.created_at,
        "last_activity": session.last_activity
    }

@app.get("/api/test_logging")
async def test_logging():
    """Test endpoint to verify logging is working"""
    logger.info("🔥 TEST LOG MESSAGE - This should appear in the terminal!")
    logger.warning("🟡 This is a warning message")
    logger.error("🔴 This is an error message")
    return {"message": "Check terminal for log messages!", "timestamp": datetime.now().isoformat()}

@app.get("/api/color_template", summary="Get color template for points")
async def get_color_template(session_id: str = Header(None, alias="X-Session-ID")):
    """Get the color template for all point numbers"""
    try:
        session = get_session(session_id)
        return {
            "status": "success",
            "color_template": session.color_template,
            "session_id": session.session_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get color template: {str(e)}")

# Serve static files (frontend) - only if build directory exists
import os
# Get absolute path to frontend build directory
current_dir = os.path.dirname(os.path.abspath(__file__))
frontend_build_path = os.path.join(current_dir, "..", "frontend", "build")
frontend_build_path = os.path.abspath(frontend_build_path)

if os.path.exists(frontend_build_path):
    app.mount("/", StaticFiles(directory=frontend_build_path, html=True), name="static")
    logging.info(f"Mounted React frontend static files from: {frontend_build_path}")
else:
    logging.warning(f"Frontend build directory not found: {frontend_build_path}")
    logging.info("Run 'npm run build' in the frontend directory to create it")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
