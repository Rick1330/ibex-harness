# authclient (Python)

Shared helpers for calling `AuthService.ValidateToken` from IBEX Python services:

- bounded protobuf wire codec (no generated stubs; see ADR-0004)
- insecure gRPC dial-target trust checks for local/mesh deployments

Consumers: `services/memory`, `services/mcp-memory`.

## Layout

```text
packages/authclient/
  pyproject.toml
  README.md
  src/
    authclient/          # import authclient
      __init__.py
      codec.py
      target.py
      permissions.py
```

Imports: `from authclient.codec import encode_validate_token_request`
