const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export type WorldResponse = {
  scenarioId: string
  projectId: string
  warehouse: {
    perimeter: Array<{ x: number; y: number }>
    boundingBox: { minX: number; minY: number; maxX: number; maxY: number }
    unit: string
  }
  obstacles: Array<{ x: number; y: number; width: number; depth: number; height: number }>
  ceiling: Array<{ xFrom: number; xTo: number; maxHeight: number }>
  rows: Array<{
    rowId: string
    bays: Array<{
      bayId: string
      typeId: number
      position: { x: number; y: number; z: number }
      rotation: number
      dimensions: { width: number; depth: number; height: number }
      nLoads: number
      price: number
    }>
  }>
  summary: { totalBays: number; totalRevenue: number }
}

export async function uploadProject(uploads: {
  warehouse: string
  obstacles: string
  ceiling: string
  bays: string
}): Promise<string> {
  const form = new FormData()
  form.append("name", `Run-${Date.now()}`)
  form.append("warehouse", new Blob([uploads.warehouse], { type: "text/csv" }), "warehouse.csv")
  form.append("obstacles", new Blob([uploads.obstacles ?? ""], { type: "text/csv" }), "obstacles.csv")
  form.append("ceiling", new Blob([uploads.ceiling], { type: "text/csv" }), "ceiling.csv")
  form.append("types_of_bays", new Blob([uploads.bays], { type: "text/csv" }), "types_of_bays.csv")

  const res = await fetch(`${API_URL}/projects`, { method: "POST", body: form })
  if (!res.ok) throw new Error(`Upload failed: ${await res.text()}`)
  const data = await res.json()
  return data.projectId as string
}

export async function createScenario(projectId: string): Promise<string> {
  const res = await fetch(`${API_URL}/projects/${projectId}/scenarios`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  })
  if (!res.ok) throw new Error(`Scenario creation failed: ${await res.text()}`)
  const data = await res.json()
  return data.scenarioId as string
}

export async function pollScenarioStatus(
  scenarioId: string,
  onStatus?: (status: string) => void,
): Promise<void> {
  for (;;) {
    const res = await fetch(`${API_URL}/scenarios/${scenarioId}/status`)
    if (!res.ok) throw new Error("Status check failed")
    const data = await res.json()
    onStatus?.(data.status)
    if (data.status === "completed") return
    if (data.status === "failed") throw new Error("Optimization failed on the server")
    await new Promise<void>(resolve => setTimeout(resolve, 2000))
  }
}

export async function fetchWorld(scenarioId: string): Promise<WorldResponse> {
  const res = await fetch(`${API_URL}/scenarios/${scenarioId}/world`)
  if (!res.ok) throw new Error("Failed to fetch world data")
  return res.json() as Promise<WorldResponse>
}
