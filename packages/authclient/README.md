# authclient (Python)

Shared helpers for calling `AuthService.ValidateToken` from IBEX Python services:

- bounded protobuf wire codec (no generated stubs; see ADR-0004)
- insecure gRPC dial-target trust checks for local/mesh deployments
- one AuthService channel factory (`authclient.channel`): TLS 1.2+ with the CA bundle in `IBEX_AUTH_GRPC_CA_FILE`, otherwise the trust-gated insecure dial (ADR-0097 §4)
- async `GRPCTokenValidator` dial client (`authclient.validate`) — management API and memory re-export it; mcp-memory wraps it to preserve MCPServiceError + `to_principal` (#779)

Consumers: `services/api`, `services/memory`, `services/mcp-memory`.

## Layout

```text
packages/authclient/
  pyproject.toml
  README.md
  src/
    authclient/          # import authclient
      __init__.py
      channel.py          # open_auth_channel / read_auth_ca / assert_auth_target
      codec.py
      target.py
      permissions.py
      errors.py
      validate.py         # GRPCTokenValidator / StaticTokenValidator
```

Imports: `from authclient import encode_validate_token_request` · `from authclient.validate import GRPCTokenValidator` · `from authclient.channel import open_auth_channel`. `channel`, `validate` and the other gRPC modules are not re-exported from the package root, so a consumer that only needs the codec or permission bitmaps can import `authclient` without `grpcio`. Install gRPC dial clients with `pip install 'authclient[grpc]'` / the service extras that depend on it.

Tests: `make test-authclient` (or `cd packages/authclient && uv run --frozen pytest -q tests`). The dev dependency group supplies pytest, ruff and grpcio; the runtime `grpc` extra stays optional.
