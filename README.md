# Interactive 3D Teeth Segmentation Web Application

A web-based interface for interactive dental segmentation using NIfTI files and nnInteractive AI models.

## Features

- **File Upload**: Drag-and-drop support for NIfTI (.nii, .nii.gz) files
- **3D Navigation**: Navigate through different axes (Sagittal, Coronal, Axial) and slices
- **Interactive Marking**: Click on images to mark teeth points with automatic numbering
- **AI Segmentation**: Integration with nnInteractive for automated segmentation
- **Download Results**: Export segmented NIfTI files and label mappings
- **Real-time Updates**: Live feedback on point marking and segmentation progress

## Architecture

### Backend (FastAPI)
- **File Processing**: NIfTI file handling with nibabel
- **API Endpoints**: RESTful API for slice extraction, point management, segmentation
- **AI Integration**: nnInteractive model integration for segmentation
- **File Management**: Secure file upload/download with temporary storage

### Frontend (React)
- **Modern UI**: Responsive design with intuitive controls
- **Canvas Rendering**: Real-time slice visualization with point overlays
- **Keyboard Navigation**: A/D for slice navigation, W/S for axis switching
- **Status Management**: Real-time feedback and error handling

## Setup and Installation

### Prerequisites
- **Python**: 3.12 or higher
- **Node.js**: 14.x or higher  
- **npm**: 6.x or higher
- **Conda**: For Python environment management (recommended)

### Installation

#### Backend Setup

**Option 1: Using conda environment (Recommended)**
```bash
# Create and activate conda environment
conda create -n teeth_segmentation python=3.12 -y
conda activate teeth_segmentation

# Navigate to backend directory
cd backend

# Install dependencies
pip install -r requirements.txt
```

**Option 2: Using existing nninteractive_env (if available)**
```bash
# Activate the pre-configured environment with all ML packages
conda activate nninteractive_env
cd backend
```

**Dependencies installed include:**
- Core packages: fastapi, uvicorn, numpy, torch, torchvision
- Medical imaging: nibabel, simpleitk, opencv-python, scikit-image
- ML frameworks: nnInteractive, nnunetv2, huggingface-hub
- Image processing: matplotlib, scipy, imageio

#### Frontend Setup
```bash
# Navigate to frontend directory
cd frontend

# Install Node.js dependencies
npm install
```

**Frontend dependencies:**
- React 18.2.0 with modern hooks and components
- axios for API communication
- Testing libraries for development

### Running the Application

#### Option 1: Auto-start (Recommended)
```bash
# From web_app directory, make the script executable
chmod +x start_app.sh

# Run the application
./start_app.sh
```

#### Option 2: Manual start
```bash
# Terminal 1: Start backend (ensure conda environment is activated)
conda activate teeth_segmentation  # or nninteractive_env
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Alternative backend startup methods:
# python start_server.py
# or: ./run_server.sh

# Terminal 2: Start frontend
cd frontend
npm start
```

The application will be available at:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs

## Usage

1. **Upload File**: Drag and drop a NIfTI file or click to browse
2. **Navigate**: Use mouse/keyboard to navigate through slices and axes
   - A/D keys: Previous/Next slice
   - W/S keys: Change axis (Sagittal → Coronal → Axial)
3. **Mark Points**: Click on teeth in the image to mark reference points
4. **Run Segmentation**: Click "Run Segmentation" to generate AI segmentation
5. **Download Results**: Download the segmented NIfTI file and label mapping

## API Endpoints

- `POST /api/upload` - Upload NIfTI file
- `GET /api/slice/{axis}/{slice_index}` - Get slice data
- `POST /api/mark_point` - Mark a point on a slice
- `DELETE /api/points` - Clear all marked points
- `POST /api/run_segmentation` - Execute segmentation
- `GET /api/download/{file_type}` - Download results
- `GET /api/file_info` - Get uploaded file information
- `GET /api/points` - Get all marked points
- `DELETE /api/point/{point_id}` - Delete specific point

## Technical Details

### File Processing
- Supports NIfTI format (.nii, .nii.gz)
- Automatic intensity normalization (0-255 range)
- Multi-axis slice extraction
- Point coordinate mapping across 3D space

### AI Integration
- nnInteractive model loading and initialization
- Automatic fallback when nnInteractive unavailable
- Point-based segmentation with configurable parameters
- Export in standard NIfTI format

### Security
- File validation and sanitization
- Temporary file cleanup
- CORS configuration for cross-origin requests
- Input validation with Pydantic models

## Development

### Project Structure
```
web_app/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── requirements.txt     # Python dependencies
│   └── temp_uploads/        # Temporary file storage
├── frontend/
│   ├── public/
│   │   └── index.html       # HTML template
│   ├── src/
│   │   ├── App.js           # Main React component
│   │   ├── index.js         # React entry point
│   │   └── index.css        # Styling
│   └── package.json         # Node.js dependencies
└── start_app.sh             # Application launcher
```

### API Development
The backend uses FastAPI with automatic OpenAPI documentation available at `/docs`. The API follows RESTful principles with proper HTTP status codes and error handling.

### Frontend Development
Built with React 18.2.0 using functional components and hooks. Features responsive design with CSS Grid and modern JavaScript (ES6+).

## Troubleshooting

### Common Issues
1. **nnInteractive not found**: The application will work without nnInteractive but segmentation will be disabled
2. **Environment activation**: Always ensure the correct conda environment is activated before starting the backend
3. **File upload fails**: Check file format (.nii or .nii.gz) and file size
4. **Port conflicts**: Modify ports in start_app.sh if 3000/8000 are in use
5. **CORS errors**: Ensure backend is running and accessible
6. **Missing dependencies**: If packages are missing, try: `pip install -r backend/requirements.txt`

### Environment Issues
If you encounter dependency conflicts:
```bash
# Create fresh environment
conda deactivate
conda remove -n teeth_segmentation --all -y
conda create -n teeth_segmentation python=3.8 -y
conda activate teeth_segmentation
cd backend && pip install -r requirements.txt
```

### GPU/CUDA Issues
For GPU acceleration (if available):
- Ensure CUDA toolkit is properly installed
- Monitor GPU memory usage during segmentation
- The environment includes NVIDIA CUDA libraries for GPU support

### Performance Tips
- Use smaller NIfTI files for faster processing
- Clear browser cache if experiencing issues
- Monitor browser console for detailed error messages

## 📦 Detailed Dependencies

### Backend Python Packages

**Core Web Framework:**
- `fastapi[all]==0.104.1` - Modern web framework for APIs
- `uvicorn[standard]==0.24.0` - ASGI server for FastAPI
- `python-multipart==0.0.6` - File upload support

**Scientific Computing:**
- `numpy==2.3.1` - Numerical computing foundation
- `scipy==1.16.0` - Scientific computing algorithms
- `pandas==2.3.1` - Data manipulation and analysis

**Medical Image Processing:**
- `nibabel==5.3.2` - Neuroimaging data I/O (NIfTI files)
- `simpleitk==2.5.2` - Medical image registration and segmentation
- `imageio==2.37.0` - Image I/O operations
- `scikit-image==0.25.2` - Image processing algorithms

**Deep Learning & AI:**
- `torch==2.7.1` - PyTorch deep learning framework  
- `torchvision==0.22.1` - Computer vision utilities
- `nnInteractive==1.0.1` - Interactive neural network inference
- `nnunetv2==2.6.2` - Medical image segmentation framework
- `huggingface-hub==0.33.4` - Model hub integration
- `timm==1.0.17` - PyTorch image models

**Computer Vision:**
- `opencv-python==4.12.0.88` - Computer vision library
- `matplotlib==3.10.3` - Plotting and visualization
- `pillow==11.3.0` - Python Imaging Library

**Data Validation:**
- `pydantic==2.4.2` - Data validation using Python type hints
- `pydantic-core==2.10.1` - Core validation logic

### Frontend Node.js Packages

**React Framework:**
- `react==^18.2.0` - React library
- `react-dom==^18.2.0` - React DOM renderer
- `react-scripts==5.0.1` - Build and development tools

**HTTP & Communication:**
- `axios==^1.5.0` - Promise-based HTTP client for API calls

**Development & Testing:**
- `@testing-library/react==^13.3.0` - React testing utilities
- `@testing-library/jest-dom==^5.16.4` - Jest DOM matchers
- `web-vitals==^2.1.4` - Performance metrics

## 🏭 Production Deployment

### Frontend Build
```bash
cd frontend
npm run build
```
Creates optimized production build in `frontend/build/` directory.

### Backend Deployment
For production deployment:
```bash
# Install production dependencies
pip install gunicorn

# Run with multiple workers
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Environment Variables
Consider setting these for production:
```bash
export PYTHONPATH=/path/to/your/app
export CUDA_VISIBLE_DEVICES=0  # For GPU usage
```

## 🧪 Testing

### Backend Testing
```bash
cd backend
python -m pytest test_sessions.py -v
```

### Frontend Testing  
```bash
cd frontend
npm test
```

### Manual Testing
Test the complete workflow:
1. Upload a sample NIfTI file
2. Navigate through different slices and axes
3. Mark several points on teeth
4. Run segmentation (if nnInteractive is available)
5. Download results
````
