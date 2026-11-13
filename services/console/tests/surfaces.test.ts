import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

import { SURFACES, type SurfaceDefinition } from "../shared/operator/surfaces"

const registryPath = path.resolve(
  import.meta.dirname,
  "../../../engineering/architecture-v2/contracts/rest-route-registry.json",
)

type RegistryRow = { contract_id: string }
const registry = JSON.parse(readFileSync(registryPath, "utf8")) as {
  routes: RegistryRow[]
  grpc_methods: RegistryRow[]
  mcp_tools: RegistryRow[]
}

const registeredContractIds = new Set(
  [...registry.routes, ...registry.grpc_methods, ...registry.mcp_tools].map(
    (row) => row.contract_id,
  ),
)

const surfaces: SurfaceDefinition[] = Object.values(SURFACES)

describe("static surface status", () => {
  it("marks only the eight validated reads as live", () => {
    const live = Object.values(SURFACES)
      .filter((surface) => surface.availability === "live")
      .map((surface) => surface.path)
      .sort()
    expect(live).toEqual([
      "/",
      "/agents",
      "/directives",
      "/evidence",
      "/explore",
      "/memories",
      "/platform",
      "/sessions",
    ])
  })

  it("keeps the remaining ten surfaces in preview", () => {
    const preview = Object.values(SURFACES)
      .filter((surface) => surface.availability === "preview")
      .map((surface) => surface.path)
      .sort()
    expect(preview).toEqual([
      "/access",
      "/analytics",
      "/audit",
      "/budgets",
      "/drift",
      "/incidents",
      "/mcp-tools",
      "/policies",
      "/providers",
      "/settings",
    ])
  })

  it("does not retain billing as a product surface", () => {
    expect(
      Object.values(SURFACES).some((surface) => surface.path === "/billing"),
    ).toBe(false)
  })

  it("keeps domains explicit and names a contract only when one is served", () => {
    for (const surface of surfaces) {
      if (surface.contractStatus === "design") {
        expect(surface.contract, surface.path).toBeUndefined()
      } else {
        expect(surface.contract, surface.path).toBeTruthy()
      }
      expect(surface.question.length, surface.path).toBeGreaterThan(0)
      expect(surface.domain, surface.path).toMatch(/^D[1-6]$/)
    }
  })
})

describe("surface contract declarations", () => {
  // R01: the declaration used to name contracts that did not exist, and nothing
  // failed. This is the gate that stops the drift recurring: every ID a surface
  // names must be a registered contract, so a surface cannot advertise a read
  // model the API does not serve.
  it("names only contract IDs that exist in the registry", () => {
    expect(registeredContractIds.size).toBeGreaterThan(0)
    for (const surface of surfaces) {
      if (!surface.contract) continue
      const declared = surface.contract.split(/\s+\+\s+/)
      expect(declared.length, surface.path).toBeGreaterThan(0)
      for (const contractId of declared) {
        expect(
          registeredContractIds.has(contractId),
          `${surface.path} declares ${contractId}, which is absent from ` +
            "engineering/architecture-v2/contracts/rest-route-registry.json",
        ).toBe(true)
      }
    }
  })

  it("marks a design-only surface instead of inventing a contract", () => {
    const design = surfaces
      .filter((surface) => surface.contractStatus === "design")
      .map((surface) => surface.path)
      .sort()
    expect(design).toEqual([
      "/access",
      "/analytics",
      "/audit",
      "/budgets",
      "/drift",
      "/incidents",
      "/mcp-tools",
      "/policies",
      "/providers",
      "/settings",
    ])
  })

  it("backs every live surface with a registry contract", () => {
    for (const surface of surfaces) {
      if (surface.availability !== "live") continue
      expect(surface.contractStatus, surface.path).toBe("registry")
      expect(surface.contract, surface.path).toBeTruthy()
    }
  })
})
