#!/usr/bin/env python3
"""
Simple test to verify frontend session integration
Tests the backend API endpoints with session headers
"""

import requests
import json
import tempfile
import os
import numpy as np
import nibabel as nib

API_BASE = "http://localhost:8000"

def test_session_creation():
    """Test session creation endpoint"""
    print("Testing session creation...")
    response = requests.post(f"{API_BASE}/api/session")
    if response.status_code == 200:
        session_data = response.json()
        session_id = session_data.get('session_id')
        print(f"✅ Session created: {session_id}")
        return session_id
    else:
        print(f"❌ Failed to create session: {response.status_code}")
        return None

def test_with_session_header(session_id):
    """Test API calls with session header"""
    headers = {'X-Session-ID': session_id}
    
    print(f"\nTesting with session ID: {session_id}")
    
    # Test status endpoint
    print("Testing status endpoint...")
    response = requests.get(f"{API_BASE}/api/status", headers=headers)
    if response.status_code == 200:
        status = response.json()
        print(f"✅ Status: {json.dumps(status, indent=2)}")
    else:
        print(f"❌ Status failed: {response.status_code}")
    
    # Create dummy NIfTI file
    print("Creating dummy NIfTI file...")
    data = np.random.randint(0, 1000, (32, 32, 32), dtype=np.int16)
    affine = np.eye(4)
    nii = nib.Nifti1Image(data, affine)
    
    with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as tmp:
        nib.save(nii, tmp.name)
        
        # Test upload with session
        print("Testing upload with session...")
        with open(tmp.name, 'rb') as f:
            files = {'file': ('test.nii.gz', f, 'application/gzip')}
            response = requests.post(f"{API_BASE}/api/upload", 
                                   files=files, headers=headers)
        
        if response.status_code == 200:
            upload_result = response.json()
            print(f"✅ Upload successful: {upload_result.get('message')}")
            print(f"   Session ID in response: {upload_result.get('session_id')}")
        else:
            print(f"❌ Upload failed: {response.status_code}")
        
        # Clean up
        os.unlink(tmp.name)
    
    # Test marking points
    print("Testing point marking...")
    point_data = {
        "axis": 2,
        "slice_index": 16,
        "point": {"x": 16, "y": 16}
    }
    response = requests.post(f"{API_BASE}/api/mark_point", 
                           json=point_data, headers=headers)
    if response.status_code == 200:
        point_result = response.json()
        print(f"✅ Point marked: {point_result.get('message')}")
        print(f"   Session ID in response: {point_result.get('session_id')}")
    else:
        print(f"❌ Point marking failed: {response.status_code}")

def test_multiple_sessions():
    """Test multiple concurrent sessions"""
    print("\n" + "="*50)
    print("Testing multiple concurrent sessions...")
    
    sessions = []
    for i in range(3):
        session_id = test_session_creation()
        if session_id:
            sessions.append(session_id)
    
    print(f"\nCreated {len(sessions)} sessions")
    
    # Test each session independently
    for i, session_id in enumerate(sessions):
        print(f"\n--- Testing session {i+1}: {session_id[:8]}... ---")
        test_with_session_header(session_id)

def main():
    print("Frontend Session Integration Test")
    print("="*50)
    
    try:
        # Test single session
        session_id = test_session_creation()
        if session_id:
            test_with_session_header(session_id)
        
        # Test multiple sessions
        test_multiple_sessions()
        
        print("\n" + "="*50)
        print("✅ All tests completed!")
        print("\nFrontend should now be able to:")
        print("- Create sessions automatically")
        print("- Include X-Session-ID header in all requests")
        print("- Handle session responses properly")
        print("- Support multiple concurrent users")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Check if required packages are available
    try:
        import requests
        import numpy as np
        import nibabel as nib
    except ImportError as e:
        print(f"Missing required package: {e}")
        print("Install with: pip install requests numpy nibabel")
        exit(1)
    
    print("Make sure the FastAPI server is running on localhost:8000")
    print("Start it with: python main.py or ./run_server.sh")
    print()
    
    main()
