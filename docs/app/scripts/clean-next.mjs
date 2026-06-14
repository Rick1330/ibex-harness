import { rmSync } from "node:fs";
import { join } from "node:path";

const nextDir = join(process.cwd(), ".next");

try {
  rmSync(nextDir, { recursive: true, force: true });
  console.log("Removed .next cache");
} catch (error) {
  console.error("Failed to remove .next cache:", error);
  process.exit(1);
}
