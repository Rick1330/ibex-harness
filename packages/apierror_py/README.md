# apierror-py

Python IBEX HTTP error envelope matching Go [`packages/apierror`](../apierror/) and
[`API_DOCUMENTATION.md`](../../web/engineering/API_DOCUMENTATION.md) “Error Response Format”.

Shape:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "...",
    "detail": "...",
    "docs_url": "...",
    "request_id": "...",
    "timestamp": "2024-01-15T10:30:45.123Z",
    "field_errors": []
  }
}
```

Import package name: `apierror_py` (directory `packages/apierror_py` avoids colliding with Go `packages/apierror`).
