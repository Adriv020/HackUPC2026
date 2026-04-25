"use client"

import { useState, useCallback, useEffect } from "react"
import {
  type WarehousePolygon,
  type ObstacleConfig,
  type CeilingProfile,
  type PlacedBay,
  type BayTypeConfig,
} from "@/lib/warehouse-service"
import { uploadProject, createScenario, pollScenarioStatus, fetchWorld } from "@/lib/api"
import { mapWorldToScene } from "@/lib/world-mapper"
import { WarehouseScene, type IntroPhase, type ExteriorMode } from "./warehouse-scene"
import { InfoPanel } from "./components/info-panel"
import { loadTestCase } from "./actions"

// ─── Types ────────────────────────────────────────────────────────────────────

type ParsedData = {
  polygon: WarehousePolygon
  obstacles: ObstacleConfig[]
  ceilingProfile: CeilingProfile
  bayTypes: BayTypeConfig[]
  placedBays: PlacedBay[]
}

type UploadState = {
  warehouse: string | null
  obstacles: string | null
  ceiling: string | null
  bays: string | null
}

const EMPTY_UPLOADS: UploadState = {
  warehouse: null,
  obstacles: null,
  ceiling: null,
  bays: null,
}

// ─── File reading helper ───────────────────────────────────────────────────────

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = e => resolve(e.target?.result as string ?? "")
    reader.onerror = () => reject(new Error(`Failed to read ${file.name}`))
    reader.readAsText(file)
  })
}

// ─── Upload card ──────────────────────────────────────────────────────────────

function UploadCard({
  label,
  desc,
  loaded,
  onChange,
}: {
  label: string
  desc: string
  loaded: boolean
  onChange: (file: File) => void
}) {
  return (
    <label
      className="flex cursor-pointer flex-col gap-2 rounded-xl border p-4 transition-colors"
      style={{
        borderColor: loaded ? "rgba(52,211,153,0.5)" : "rgba(15,23,42,0.15)",
        background: loaded ? "rgba(209,250,229,0.8)" : "rgba(255,255,255,0.6)",
      }}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-900">{label}</span>
        {loaded && <span className="text-xs text-emerald-600">✓ Loaded</span>}
      </div>
      <p className="text-xs" style={{ color: "rgba(15,23,42,0.6)" }}>{desc}</p>
      <input
        type="file"
        accept=".csv,text/csv,text/plain"
        className="hidden"
        onChange={e => {
          const file = e.target.files?.[0]
          if (file) onChange(file)
        }}
      />
      <div
        className="rounded border border-dashed px-3 py-2 text-center text-xs"
        style={{
          borderColor: loaded ? "rgba(52,211,153,0.5)" : "rgba(15,23,42,0.25)",
          color: loaded ? "rgba(5,150,105,0.8)" : "rgba(15,23,42,0.6)",
        }}
      >
        {loaded ? "Click to replace" : "Click to upload"}
      </div>
    </label>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export function WarehousePlayground() {
  const [uploads, setUploads] = useState<UploadState>(EMPTY_UPLOADS)
  const [parsedData, setParsedData] = useState<ParsedData | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [loadingMessage, setLoadingMessage] = useState("Working…")
  const [error, setError] = useState<string | null>(null)
  const [introPhase, setIntroPhase] = useState<IntroPhase>("intro_orbit")
  const [introStartMs, setIntroStartMs] = useState(0)
  const [selectedBayId, setSelectedBayId] = useState<string | null>(null)

  // New state for exterior visibility control
  const [exteriorMode, setExteriorMode] = useState<ExteriorMode>("auto")
  const [isExteriorMenuOpen, setIsExteriorMenuOpen] = useState(false)

  const allUploaded = Object.values(uploads).every(v => v !== null)

  // Send CSVs to backend, run SA solver, fetch results from MongoDB
  useEffect(() => {
    if (!allUploaded) return
    let cancelled = false
    setIsLoading(true)
    setError(null)

    async function run() {
      try {
        setLoadingMessage("Uploading files to backend…")
        const projectId = await uploadProject(uploads as Required<UploadState>)
        if (cancelled) return

        setLoadingMessage("Starting optimization…")
        const scenarioId = await createScenario(projectId)
        if (cancelled) return

        setLoadingMessage("Solver running — this takes ~3 min…")
        await pollScenarioStatus(scenarioId)
        if (cancelled) return

        setLoadingMessage("Loading results from MongoDB…")
        const world = await fetchWorld(scenarioId)
        if (cancelled) return

        const { polygon, obstacles, ceilingProfile, placedBays, bayTypes } = mapWorldToScene(world)
        console.log(`[WarehouseOS] ${placedBays.length} bays loaded from MongoDB`)

        setParsedData({ polygon, obstacles, ceilingProfile, bayTypes, placedBays })
        setIntroStartMs(performance.now())
        setIntroPhase("intro_orbit")
        setSelectedBayId(null)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to connect to backend")
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    run()
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uploads])

  // ── File upload handlers ───────────────────────────────────────────────────

  async function handleFileChange(field: keyof UploadState, file: File) {
    const text = await readFileAsText(file)
    setUploads(prev => ({ ...prev, [field]: text }))
  }

  async function handleLoadTestCase(n: number) {
    setIsLoading(true)
    setError(null)
    try {
      const data = await loadTestCase(n)
      setUploads({
        warehouse: data.warehouse,
        obstacles: data.obstacles,
        ceiling: data.ceiling,
        bays: data.bays,
      })
    } catch {
      setError(`Could not load test case ${n} — check PublicTestCases/Case${n} exists`)
      setIsLoading(false)
    }
  }

  function handleReset() {
    setParsedData(null)
    setUploads(EMPTY_UPLOADS)
    setSelectedBayId(null)
    setError(null)
  }

  // ── Callbacks ─────────────────────────────────────────────────────────────

  const handleIntroDone = useCallback(() => setIntroPhase("interactive"), [])
  const handleClearSelection = useCallback(() => setSelectedBayId(null), [])
  const handleSelectBay = useCallback((bayId: string) => setSelectedBayId(bayId), [])

  // Find the selected bay object for the info panel
  const selectedBay = selectedBayId
    ? (parsedData?.placedBays.find(b => b.id === selectedBayId) ?? null)
    : null

  // ── 3D View ───────────────────────────────────────────────────────────────

  if (parsedData && !isLoading) {
    return (
      <div
        className="relative h-svh w-full overflow-hidden"
        style={{ background: "linear-gradient(to bottom, #76d0f5 0%, #f4f8fa 100%)" }}
      >
        {/* R3F canvas fills the screen */}
        <div className="absolute inset-0">
          <WarehouseScene
            polygon={parsedData.polygon}
            obstacles={parsedData.obstacles}
            ceilingProfile={parsedData.ceilingProfile}
            placedBays={parsedData.placedBays}
            introPhase={introPhase}
            introStartMs={introStartMs}
            onIntroDone={handleIntroDone}
            selectedBayId={selectedBayId}
            onSelectBay={handleSelectBay}
            onClearSelection={handleClearSelection}
            exteriorMode={exteriorMode}
          />
        </div>

        {/* ── Back button ─────────────────────────────────────────────────── */}
        <div className="pointer-events-auto absolute top-4 left-4 z-20">
          <button
            onClick={handleReset}
            className="rounded-full border px-4 py-2 text-sm backdrop-blur transition-colors hover:bg-white/80"
            style={{
              borderColor: "rgba(15,23,42,0.15)",
              background: "rgba(255,255,255,0.6)",
              color: "rgba(15,23,42,0.8)",
            }}
          >
            ← Upload New Files
          </button>
        </div>

        {/* ── Status chip ─────────────────────────────────────────────────── */}
        <div className="pointer-events-none absolute top-4 right-4 z-20 flex flex-col items-end gap-2">
          <div
            className="rounded-full border px-3 py-1 text-xs font-medium tracking-wide backdrop-blur"
            style={{
              borderColor: "rgba(15,23,42,0.1)",
              background: "rgba(255,255,255,0.4)",
              color: "rgba(15,23,42,0.7)",
            }}
          >
            WarehouseOS · {parsedData.placedBays.length} bays · drag to orbit · scroll to zoom
          </div>
          <div
            className="rounded-full border px-3 py-1 text-xs font-semibold backdrop-blur"
            style={{
              borderColor: "rgba(15,23,42,0.15)",
              background: "rgba(255,255,255,0.5)",
              color: "#3b82f6",
            }}
          >
            {parsedData.placedBays.length} / {parsedData.bayTypes.reduce((s, t) => s + t.count, 0)} bays placed
          </div>
        </div>

        {/* ── Exterior Controls ────────────────────────────────────────────── */}
        <div className="pointer-events-auto absolute top-24 right-4 z-20 flex flex-col items-end">
          <button
            onClick={() => setIsExteriorMenuOpen(prev => !prev)}
            className="rounded-full border px-4 py-2 text-sm backdrop-blur transition-colors hover:bg-white/80"
            style={{
              borderColor: "rgba(15,23,42,0.15)",
              background: "rgba(255,255,255,0.6)",
              color: "rgba(15,23,42,0.8)",
            }}
          >
            Exterior: <span className="capitalize">{exteriorMode}</span> ▾
          </button>
          
          {isExteriorMenuOpen && (
            <div className="mt-2 flex flex-col overflow-hidden rounded-lg border backdrop-blur"
              style={{
                borderColor: "rgba(15,23,42,0.15)",
                background: "rgba(255,255,255,0.8)",
              }}
            >
              {(["auto", "hidden", "translucent"] as ExteriorMode[]).map(mode => (
                <button
                  key={mode}
                  onClick={() => { setExteriorMode(mode); setIsExteriorMenuOpen(false) }}
                  className="px-4 py-2 text-sm text-left hover:bg-black/5 capitalize transition-colors"
                  style={{
                    color: exteriorMode === mode ? "#000" : "rgba(15,23,42,0.7)",
                    fontWeight: exteriorMode === mode ? 600 : 400
                  }}
                >
                  {mode}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* ── Info panel — shown when a bay is selected ──────────────────── */}
        {selectedBay && (
          <div className="pointer-events-auto">
            <InfoPanel
              bay={selectedBay}
              onClearSelection={handleClearSelection}
            />
          </div>
        )}
      </div>
    )
  }

  // ── Upload UI ─────────────────────────────────────────────────────────────

  return (
    <div
      className="flex min-h-svh flex-col items-center justify-center p-6"
      style={{ background: "linear-gradient(to bottom, #76d0f5 0%, #f4f8fa 100%)" }}
    >
      <div className="w-full max-w-2xl space-y-6">

        {/* Header */}
        <div className="text-center">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">WarehouseOS</h1>
          <p className="mt-2 text-sm" style={{ color: "rgba(15,23,42,0.6)" }}>
            Upload your four CSV files to build the 3D scene
          </p>
        </div>

        {/* Quick-load test cases */}
        <div className="flex items-center justify-center gap-3">
          <span className="text-xs" style={{ color: "rgba(15,23,42,0.6)" }}>
            Quick load:
          </span>
          {[0, 1, 2, 3].map(n => (
            <button
              key={n}
              onClick={() => handleLoadTestCase(n)}
              disabled={isLoading}
              className="rounded border px-3 py-1 text-xs transition-colors disabled:opacity-40 hover:bg-white/40"
              style={{
                borderColor: "rgba(15,23,42,0.2)",
                background: "rgba(255,255,255,0.5)",
                color: "rgba(15,23,42,0.8)",
              }}
            >
              Case {n}
            </button>
          ))}
        </div>

        {/* Divider */}
        <div className="flex items-center gap-3">
          <div className="h-px flex-1" style={{ background: "rgba(15,23,42,0.15)" }} />
          <span className="text-xs" style={{ color: "rgba(15,23,42,0.4)" }}>or upload manually</span>
          <div className="h-px flex-1" style={{ background: "rgba(15,23,42,0.15)" }} />
        </div>

        {/* File upload cards */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <UploadCard
            label="warehouse.csv"
            desc="Ordered polygon corner coordinates (coordX, coordY)"
            loaded={uploads.warehouse !== null}
            onChange={f => handleFileChange("warehouse", f)}
          />
          <UploadCard
            label="obstacles.csv"
            desc="Pillars & fixed equipment (coordX, coordY, width, depth)"
            loaded={uploads.obstacles !== null}
            onChange={f => handleFileChange("obstacles", f)}
          />
          <UploadCard
            label="ceiling.csv"
            desc="Variable ceiling height profile (coordX, ceilingHeight)"
            loaded={uploads.ceiling !== null}
            onChange={f => handleFileChange("ceiling", f)}
          />
          <UploadCard
            label="types_of_bays.csv"
            desc="Bay type definitions (type_id, width, depth, height, col4, count, col6)"
            loaded={uploads.bays !== null}
            onChange={f => handleFileChange("bays", f)}
          />
        </div>

        {/* Progress indicator */}
        <div className="flex items-center justify-center gap-1.5">
          {(["warehouse", "obstacles", "ceiling", "bays"] as const).map(k => (
            <div
              key={k}
              className="h-1.5 w-1.5 rounded-full transition-colors"
              style={{
                background: uploads[k] !== null
                  ? "rgba(5,150,105,0.8)"
                  : "rgba(15,23,42,0.2)",
              }}
            />
          ))}
          <span className="ml-2 text-xs" style={{ color: "rgba(15,23,42,0.6)" }}>
            {Object.values(uploads).filter(v => v !== null).length} / 4 loaded
          </span>
        </div>

        {/* Error */}
        {error && (
          <div
            className="rounded-lg border p-3 text-sm"
            style={{
              borderColor: "rgba(239,68,68,0.3)",
              background: "rgba(127,29,29,0.2)",
              color: "rgba(252,165,165,0.9)",
            }}
          >
            {error}
          </div>
        )}

        {/* Loading */}
        {isLoading && (
          <div
            className="text-center text-sm"
            style={{ color: "rgba(15,23,42,0.6)" }}
          >
            {loadingMessage}
          </div>
        )}
      </div>
    </div>
  )
}
