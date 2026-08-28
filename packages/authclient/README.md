# authclient (Python)

Shared helpers for calling `AuthService.ValidateToken` from IBEX Python services:

- bounded protobuf wire codec (no generated stubs; see ADR-0004)
- insecure gRPC dial-target trust checks for local/mesh deployments

Consumers: `services/memory`, `services/mcp-memory`.
