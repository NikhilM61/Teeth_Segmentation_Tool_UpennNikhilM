#!/bin/bash
"""
Deployment script for session-based multi-user segmentation backend
"""

set -e

echo "🚀 Starting Session-Based Multi-User Segmentation Backend"
echo "=================================================================="

# Check if we're in the right directory
if [ ! -f "main.py" ]; then
    echo "❌ Error: main.py not found. Please run this script from the backend directory."
    exit 1
fi

# Check Python version
echo "📋 Checking Python version..."
python3 --version

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install/upgrade dependencies
echo "📦 Installing dependencies..."
pip install --upgrade pip

# Core dependencies
pip install fastapi uvicorn
pip install numpy nibabel
pip install python-multipart  # For file uploads
pip install aiofiles  # For async file operations

# Optional dependencies
echo "📦 Installing optional dependencies..."
pip install torch || echo "⚠️  Warning: Could not install PyTorch - GPU features may not work"
pip install huggingface-hub || echo "⚠️  Warning: Could not install huggingface-hub"

# Try to install nnInteractive if available
echo "📦 Attempting to install nnInteractive..."
pip install nnInteractive || echo "⚠️  Warning: nnInteractive not available - will use mock segmentation"

# Development dependencies for testing
echo "📦 Installing development dependencies..."
pip install aiohttp pytest httpx || echo "⚠️  Warning: Some development dependencies failed to install"

echo ""
echo "✅ Setup complete!"
echo ""
echo "🎯 Features enabled:"
echo "   - ✅ Session-based multi-user support"
echo "   - ✅ Concurrent file processing"
echo "   - ✅ Automatic session cleanup"
echo "   - ✅ FastAPI backend with CORS"
echo "   - ✅ File upload and download"
echo "   - ✅ Mock segmentation"

# Check for GPU support
if python3 -c "import torch; print('CUDA available:', torch.cuda.is_available())" 2>/dev/null; then
    echo "   - ✅ GPU/CUDA support detected"
else
    echo "   - ⚠️  GPU/CUDA not available - using CPU mode"
fi

# Check for nnInteractive
if python3 -c "import nnInteractive" 2>/dev/null; then
    echo "   - ✅ nnInteractive available"
else
    echo "   - ⚠️  nnInteractive not available - using mock segmentation only"
fi

echo ""
echo "🚀 Starting the server..."
echo "   Server will be available at: http://localhost:8000"
echo "   API documentation: http://localhost:8000/docs"
echo "   Session management: http://localhost:8000/api/sessions"
echo ""
echo "📝 Session features:"
echo "   - Each user gets an isolated session"
echo "   - Sessions auto-expire after 24 hours of inactivity"
echo "   - Multiple users can work on different files simultaneously"
echo "   - Session IDs are passed via X-Session-ID header"
echo ""
echo "🧪 Testing:"
echo "   - Open demo_frontend.html in a browser"
echo "   - Run: python test_sessions.py (after server is running)"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the server
python3 main.py
