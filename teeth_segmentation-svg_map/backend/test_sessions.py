#!/usr/bin/env python3
"""
Test script for session-based multi-user functionality
Demonstrates how multiple sessions can work concurrently
"""

import asyncio
import aiohttp
import json
import tempfile
import os
from pathlib import Path

class SessionClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session_id = None
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def create_session(self):
        """Create a new session"""
        async with self.session.post(f"{self.base_url}/api/session") as resp:
            data = await resp.json()
            self.session_id = data["session_id"]
            print(f"Created session: {self.session_id}")
            return self.session_id
    
    def get_headers(self):
        """Get headers with session ID"""
        headers = {}
        if self.session_id:
            headers["X-Session-ID"] = self.session_id
        return headers
    
    async def upload_dummy_nifti(self, name="test"):
        """Upload a dummy NIfTI file for testing"""
        # Create a simple dummy NIfTI file
        import numpy as np
        import nibabel as nib
        
        # Create dummy 3D data
        data = np.random.randint(0, 1000, (64, 64, 64), dtype=np.int16)
        affine = np.eye(4)
        nii = nib.Nifti1Image(data, affine)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=f"_{name}.nii.gz", delete=False) as tmp:
            nib.save(nii, tmp.name)
            
            # Upload the file
            with open(tmp.name, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename=f"{name}.nii.gz", 
                             content_type='application/gzip')
                
                async with self.session.post(
                    f"{self.base_url}/api/upload",
                    data=data,
                    headers=self.get_headers()
                ) as resp:
                    result = await resp.json()
                    print(f"Upload result for {name}: {result}")
                    
            # Clean up
            os.unlink(tmp.name)
            return result
    
    async def mark_points(self, num_points=3):
        """Mark some test points"""
        points = []
        for i in range(num_points):
            point_data = {
                "axis": 2,
                "slice_index": 32,
                "point": {"x": 10 + i * 5, "y": 10 + i * 5}
            }
            
            async with self.session.post(
                f"{self.base_url}/api/mark_point",
                json=point_data,
                headers=self.get_headers()
            ) as resp:
                result = await resp.json()
                points.append(result)
                print(f"Marked point {i+1}: {result}")
        
        return points
    
    async def get_status(self):
        """Get session status"""
        async with self.session.get(
            f"{self.base_url}/api/status",
            headers=self.get_headers()
        ) as resp:
            status = await resp.json()
            print(f"Session {self.session_id} status: {status}")
            return status
    
    async def run_segmentation(self):
        """Run segmentation"""
        async with self.session.post(
            f"{self.base_url}/api/run_segmentation",
            headers=self.get_headers()
        ) as resp:
            result = await resp.json()
            print(f"Segmentation result: {result}")
            return result
    
    async def list_sessions(self):
        """List all sessions"""
        async with self.session.get(f"{self.base_url}/api/sessions") as resp:
            sessions = await resp.json()
            print(f"All sessions: {json.dumps(sessions, indent=2, default=str)}")
            return sessions

async def test_single_session():
    """Test single session workflow"""
    print("\n=== Testing Single Session ===")
    
    async with SessionClient() as client:
        # Create session
        await client.create_session()
        
        # Upload file
        await client.upload_dummy_nifti("single_session")
        
        # Mark points
        await client.mark_points(3)
        
        # Get status
        await client.get_status()
        
        # Run segmentation
        await client.run_segmentation()

async def test_multiple_sessions():
    """Test multiple concurrent sessions"""
    print("\n=== Testing Multiple Concurrent Sessions ===")
    
    # Create multiple clients
    clients = []
    for i in range(3):
        client = SessionClient()
        await client.__aenter__()
        clients.append(client)
    
    try:
        # Create sessions for all clients
        tasks = []
        for i, client in enumerate(clients):
            tasks.append(client.create_session())
        await asyncio.gather(*tasks)
        
        # Upload different files concurrently
        tasks = []
        for i, client in enumerate(clients):
            tasks.append(client.upload_dummy_nifti(f"user_{i+1}"))
        await asyncio.gather(*tasks)
        
        # Mark points concurrently
        tasks = []
        for i, client in enumerate(clients):
            tasks.append(client.mark_points(2 + i))
        await asyncio.gather(*tasks)
        
        # Get status for all sessions
        tasks = []
        for client in clients:
            tasks.append(client.get_status())
        await asyncio.gather(*tasks)
        
        # List all sessions
        await clients[0].list_sessions()
        
        # Run segmentation concurrently
        tasks = []
        for client in clients:
            tasks.append(client.run_segmentation())
        results = await asyncio.gather(*tasks)
        
        print(f"\nAll segmentations completed: {len(results)} results")
        
    finally:
        # Clean up clients
        for client in clients:
            await client.__aexit__(None, None, None)

async def test_session_isolation():
    """Test that sessions are properly isolated"""
    print("\n=== Testing Session Isolation ===")
    
    async with SessionClient() as client1, SessionClient() as client2:
        # Create separate sessions
        await client1.create_session()
        await client2.create_session()
        
        # Upload different files
        await client1.upload_dummy_nifti("isolation_test_1")
        await client2.upload_dummy_nifti("isolation_test_2")
        
        # Mark different numbers of points
        await client1.mark_points(2)
        await client2.mark_points(4)
        
        # Check that each session has its own data
        status1 = await client1.get_status()
        status2 = await client2.get_status()
        
        print(f"Session 1 points: {status1['total_points']}")
        print(f"Session 2 points: {status2['total_points']}")
        
        assert status1['total_points'] == 2, f"Expected 2 points, got {status1['total_points']}"
        assert status2['total_points'] == 4, f"Expected 4 points, got {status2['total_points']}"
        assert status1['session_id'] != status2['session_id'], "Sessions should have different IDs"
        
        print("✅ Session isolation test passed!")

async def main():
    """Run all tests"""
    print("Starting Session-Based Multi-User Tests")
    print("=" * 50)
    
    try:
        # Test single session
        await test_single_session()
        
        # Test multiple sessions
        await test_multiple_sessions()
        
        # Test session isolation
        await test_session_isolation()
        
        print("\n" + "=" * 50)
        print("All tests completed successfully! 🎉")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Note: This requires the server to be running
    print("Make sure the FastAPI server is running on localhost:8000")
    print("Start it with: python main.py")
    print()
    
    # Check if required packages are available
    try:
        import aiohttp
        import numpy as np
        import nibabel as nib
    except ImportError as e:
        print(f"Missing required package: {e}")
        print("Install with: pip install aiohttp numpy nibabel")
        exit(1)
    
    asyncio.run(main())
