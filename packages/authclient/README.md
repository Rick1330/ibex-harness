# authclient (Python)

Shared helpers for calling `AuthService.ValidateToken` from IBEX Python services:

- bounded protobuf wire codec (no generated stubs; see ADR-0004)
- insecure gRPC dial-target trust checks for local/mesh deployments
- async `GRPCTokenValidator` dial client (`authclient.validate`) — management API and memory re-export it; mcp-memory wraps it to preserve MCPServiceError + `to_principal` (#779)

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
      errors.py
      validate.py         # GRPCTokenValidator / StaticTokenValidator
```

Imports: `from authclient import encode_validate_token_request` · `from authclient.validate import GRPCTokenValidator` (validate is not re-exported from the package root so consumers without grpcio can still import the codec).
