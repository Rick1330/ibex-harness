"""HTTP mapping for GET /v1/memories/{id}/lineage (milestone 5.B.1)."""

from __future__ import annotations

from app.read.lineage import LineageResult
from app.schemas.lineage import (
    LineageEdgeSchema,
    LineageEndpointSchema,
    MemoryLineageData,
    MemoryLineageResponse,
)


def lineage_response_from_result(result: LineageResult) -> MemoryLineageResponse:
    return MemoryLineageResponse(
        data=MemoryLineageData(
            memory_id=result.root.memory_id,
            status=result.root.status,
            tombstoned=result.root.tombstoned,
            supersession_tip=result.root.supersession_tip,
            max_depth=result.max_depth,
            truncated=result.truncated,
            edges=[
                LineageEdgeSchema(
                    source_memory_id=edge.source_memory_id,
                    target_memory_id=edge.target_memory_id,
                    relationship_type=edge.relationship_type,  # type: ignore[arg-type]
                    confidence=edge.confidence,
                    depth=edge.depth,
                    from_memory_id=edge.from_memory_id,
                    other=LineageEndpointSchema(
                        memory_id=edge.other.memory_id,
                        status=edge.other.status,
                        tombstoned=edge.other.tombstoned,
                    ),
                )
                for edge in result.edges
            ],
        )
    )
