## ADDED Requirements

### Requirement: Legacy upload endpoint returns 410 Gone
The system SHALL return `410 Gone` for `POST /api/upload` with response body matching the unified error format per `spec.md §4.9`.

#### Scenario: POST /api/upload returns 410
- **WHEN** a client sends `POST /api/upload`
- **THEN** the system returns HTTP 410 with JSON body `{"error": "This API endpoint has been removed", "code": "GONE", "request_id": "<uuid-v4>"}`

### Requirement: Legacy search endpoint returns 410 Gone
The system SHALL return `410 Gone` for `GET /api/search` with unified error response body.

#### Scenario: GET /api/search returns 410
- **WHEN** a client sends `GET /api/search`
- **THEN** the system returns HTTP 410 with JSON body `{"error": "This API endpoint has been removed", "code": "GONE", "request_id": "<uuid-v4>"}`

### Requirement: Legacy queue status endpoint returns 410 Gone
The system SHALL return `410 Gone` for `GET /api/queue/status` with unified error response body.

#### Scenario: GET /api/queue/status returns 410
- **WHEN** a client sends `GET /api/queue/status`
- **THEN** the system returns HTTP 410 with JSON body `{"error": "This API endpoint has been removed", "code": "GONE", "request_id": "<uuid-v4>"}`

### Requirement: Legacy health endpoint returns 410 Gone
The system SHALL return `410 Gone` for `GET /api/health` with unified error response body.

#### Scenario: GET /api/health returns 410
- **WHEN** a client sends `GET /api/health`
- **THEN** the system returns HTTP 410 with JSON body `{"error": "This API endpoint has been removed", "code": "GONE", "request_id": "<uuid-v4>"}`

### Requirement: No deprecated log entries after 410 transition
The system SHALL NOT log `[DEPRECATED]` messages for legacy endpoint requests after they return 410 Gone.

#### Scenario: No DEPRECATED log for 410 responses
- **WHEN** a client sends any request to the 4 legacy endpoints
- **THEN** the server logs do NOT contain `[DEPRECATED]` entries for that request
