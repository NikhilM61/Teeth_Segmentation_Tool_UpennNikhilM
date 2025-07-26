# Session-Based Multi-User Support

## Overview

The FastAPI backend has been updated to support concurrent sessions, allowing multiple users to work on different NIfTI files simultaneously. Each user session is isolated with its own state, data, and processing pipeline.

## Key Features

### 1. Session Management
- **Automatic Session Creation**: Sessions are created automatically when a user first accesses the API
- **Session Isolation**: Each session has its own NIfTI data, marked points, and segmentation results
- **Session Cleanup**: Automatic cleanup of expired sessions (24-hour timeout by default)
- **Session Persistence**: Sessions remain active as long as they're being used

### 2. Multi-User Concurrency
- **Independent Processing**: Multiple users can upload and process different files simultaneously
- **Resource Isolation**: Each session's data is completely isolated from others
- **Concurrent Segmentation**: Multiple segmentation processes can run in parallel
- **File Management**: Each session has its own temporary files and output directories

### 3. Session Lifecycle Management
- **Creation**: Sessions created on-demand via API calls
- **Activity Tracking**: Last activity timestamp updated on each API call
- **Expiration**: Sessions automatically cleaned up after 24 hours of inactivity
- **Manual Deletion**: Sessions can be explicitly deleted via API

## API Changes

### Session Headers
All API endpoints now support an optional `X-Session-ID` header:
```http
X-Session-ID: your-session-id-here
```

If no session ID is provided, a new session will be created automatically.

### New Session Management Endpoints

#### Create Session
```http
POST /api/session
```
Returns:
```json
{
  "session_id": "uuid4-session-id"
}
```

#### List Sessions
```http
GET /api/sessions
```
Returns:
```json
{
  "sessions": [
    {
      "session_id": "uuid4-session-id",
      "created_at": "2025-01-01T12:00:00",
      "last_activity": "2025-01-01T12:30:00",
      "nifti_loaded": true,
      "nifti_shape": [512, 512, 300],
      "total_points": 5
    }
  ]
}
```

#### Delete Session
```http
DELETE /api/session/{session_id}
```

### Updated Endpoints
All existing endpoints now include session information in responses:

#### Status Endpoint
```http
GET /api/status
```
Returns:
```json
{
  "session_id": "uuid4-session-id",
  "nifti_loaded": true,
  "nifti_shape": [512, 512, 300],
  "total_points": 3,
  "nninteractive_available": true,
  "cuda_available": true,
  "segmentation_files": false,
  "created_at": "2025-01-01T12:00:00",
  "last_activity": "2025-01-01T12:30:00"
}
```

#### Upload Response
```http
POST /api/upload
```
Returns:
```json
{
  "message": "File uploaded successfully",
  "session_id": "uuid4-session-id",
  "shape": [512, 512, 300],
  "data_range": [-1024, 3071]
}
```

## Frontend Integration

### 1. Session ID Management
The frontend should:
- Store the session ID (in localStorage, sessionStorage, or state management)
- Include the session ID in all API calls via the `X-Session-ID` header
- Handle session creation on first load
- Provide session management UI for power users

### 2. Example Frontend Implementation
```javascript
class SessionManager {
  constructor() {
    this.sessionId = localStorage.getItem('sessionId');
  }
  
  async getSessionId() {
    if (!this.sessionId) {
      const response = await fetch('/api/session', { method: 'POST' });
      const data = await response.json();
      this.sessionId = data.session_id;
      localStorage.setItem('sessionId', this.sessionId);
    }
    return this.sessionId;
  }
  
  getHeaders() {
    return {
      'X-Session-ID': this.sessionId,
      'Content-Type': 'application/json'
    };
  }
  
  async apiCall(url, options = {}) {
    await this.getSessionId();
    const headers = { ...this.getHeaders(), ...options.headers };
    return fetch(url, { ...options, headers });
  }
}

// Usage
const sessionManager = new SessionManager();

// Upload file with session
const formData = new FormData();
formData.append('file', file);
const response = await sessionManager.apiCall('/api/upload', {
  method: 'POST',
  body: formData,
  headers: {} // Don't set Content-Type for FormData
});
```

### 3. Multi-Tab Support
With session-based architecture, users can:
- Open multiple tabs with different sessions
- Work on different files simultaneously
- Share session IDs between tabs for collaboration

## Backend Architecture

### 1. Session State
```python
class SessionState:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.nifti_data = None
        self.nifti_affine = None
        self.nifti_header = None
        self.marked_points_2d = {}
        self.all_3d_points = []
        # ... other session-specific data
```

### 2. Session Manager
```python
class SessionManager:
    def __init__(self, session_timeout_hours=24):
        self.sessions = {}
        self.session_timeout = timedelta(hours=session_timeout_hours)
        # Automatic cleanup thread
```

### 3. Dependency Injection
FastAPI dependency injection manages session retrieval:
```python
def get_session(session_id: str = Depends(get_session_id)) -> SessionState:
    return session_manager.get_session(session_id)

@app.post("/api/upload")
async def upload_nifti(file: UploadFile, session: SessionState = Depends(get_session)):
    # Session is automatically injected
```

## Configuration

### Session Timeout
Default: 24 hours of inactivity
```python
session_manager = SessionManager(session_timeout_hours=24)
```

### Memory Management
- Sessions are cleaned up automatically
- Temporary files are removed on session deletion
- nnInteractive sessions are properly disposed

## Security Considerations

### 1. Session ID Security
- UUIDs used for session IDs (cryptographically secure)
- Session IDs are not predictable
- No sensitive data stored in session IDs

### 2. Resource Limits
- File size limits remain in place (500MB per upload)
- Session timeout prevents indefinite resource usage
- Temporary file cleanup prevents disk space issues

### 3. Access Control
- Sessions are isolated - no cross-session data access
- No user authentication required (sessions are anonymous)
- Session deletion requires exact session ID

## Monitoring and Logging

### 1. Session Metrics
- Number of active sessions
- Session creation/deletion rates
- Resource usage per session

### 2. Logging
- Session lifecycle events
- Per-session operation logging
- Error tracking with session context

## Migration from Single-User

### Breaking Changes
- API responses now include `session_id` field
- Session management endpoints added
- Frontend must handle session IDs

### Backward Compatibility
- APIs work without session headers (auto-create session)
- Existing functionality preserved
- Gradual migration possible

## Deployment Considerations

### 1. Scaling
- Sessions are stored in memory (consider Redis for multi-instance)
- Each instance manages its own sessions
- Load balancer should use sticky sessions

### 2. High Availability
- Session persistence not implemented (sessions lost on restart)
- Consider Redis/database for session persistence
- Graceful shutdown should clean up sessions

### 3. Resource Planning
- Memory usage scales with number of active sessions
- Disk usage for temporary files per session
- GPU resources shared across sessions
