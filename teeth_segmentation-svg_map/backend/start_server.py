#!/usr/bin/env python
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try to start the server
try:
    import uvicorn
    from main import app
    
    print("Starting FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
    
except ImportError as e:
    print(f"Import error: {e}")
    print("Trying to install missing dependencies...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "uvicorn[standard]"])
    
    # Try again
    import uvicorn
    from main import app
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
