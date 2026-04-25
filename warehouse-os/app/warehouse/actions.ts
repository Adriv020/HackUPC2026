"use server"

import { readFile } from "node:fs/promises"
import { join } from "node:path"

// PublicTestCases lives one directory above the Next.js project root
const CASES_DIR = join(process.cwd(), "..", "PublicTestCases")

export type TestCaseData = {
  warehouse: string
  obstacles: string
  ceiling: string
  bays: string
}

export async function loadTestCase(caseNum: number): Promise<TestCaseData> {
  const dir = join(CASES_DIR, `Case${caseNum}`)
  const [warehouse, obstacles, ceiling, bays] = await Promise.all([
    readFile(join(dir, "warehouse.csv"), "utf-8"),
    // obstacles.csv may be empty in some test cases (e.g. Case1)
    readFile(join(dir, "obstacles.csv"), "utf-8").catch(() => ""),
    readFile(join(dir, "ceiling.csv"), "utf-8"),
    readFile(join(dir, "types_of_bays.csv"), "utf-8"),
  ])
  return { warehouse, obstacles, ceiling, bays }
}
