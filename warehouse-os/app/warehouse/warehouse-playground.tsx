"use client"

import { useState, useCallback, useEffect } from "react"
import {
  type WarehousePolygon,
  type ObstacleConfig,
  type CeilingProfile,
  type PlacedBay,
  type BayTypeConfig,
} from "@/lib/warehouse-service"
import { solve, type WorldResponse } from "@/lib/api"
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

export type ViewMode = "3d" | "floor_plan"

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
  const [viewMode, setViewMode] = useState<ViewMode>("3d")
  const [algorithm, setAlgorithm] = useState<"python" | "cpp">("cpp")

  // Splash title card shown on load
  const [splashPhase, setSplashPhase] = useState<"visible" | "fading" | "hidden">("hidden")
  const [splashCase, setSplashCase] = useState<string | null>(null)

  const allUploaded = Object.values(uploads).every(v => v !== null)

  // On mount: if opened via SA dashboard (?preload=CaseN), fetch world data directly
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const preloadCase = params.get("preload")
    if (!preloadCase) return

    setIsLoading(true)
    setLoadingMessage("Loading 3D scene…")
    setError(null)
    setSplashCase(preloadCase)

    fetch(`http://localhost:8000/api/3dview?case=${encodeURIComponent(preloadCase)}`)
      .then(res => {
        if (!res.ok) return res.text().then(t => { throw new Error(t) })
        return res.json() as Promise<WorldResponse>
      })
      .then(world => {
        const { polygon, obstacles, ceilingProfile, placedBays, bayTypes } = mapWorldToScene(world)
        // Park the intro animation at t=0 (start position) until the splash clears.
        // SPLASH_VISIBLE(2200) + FADE(700) = 2900 ms before elapsed goes positive.
        const splashMs = 2200 + 700
        setIntroStartMs(performance.now() + splashMs)
        setIntroPhase("intro_orbit")
        setParsedData({ polygon, obstacles, ceilingProfile, bayTypes, placedBays })
        setSplashPhase("visible")
        setIsLoading(false)
      })
      .catch(err => {
        setError(err instanceof Error ? err.message : "Failed to load scene from SA dashboard")
        setIsLoading(false)
      })
  }, [])

  // Splash timing: hold for 2.2 s then fade
  useEffect(() => {
    if (splashPhase !== "visible") return
    const t = setTimeout(() => setSplashPhase("fading"), 2200)
    return () => clearTimeout(t)
  }, [splashPhase])

  // After fade transition completes, remove the overlay from the DOM
  useEffect(() => {
    if (splashPhase !== "fading") return
    const t = setTimeout(() => setSplashPhase("hidden"), 700)
    return () => clearTimeout(t)
  }, [splashPhase])

  // Send CSVs to backend, run SA solver, return world JSON directly
  useEffect(() => {
    if (!allUploaded) return
    let cancelled = false
    setIsLoading(true)
    setError(null)

    async function run() {
      try {
        setLoadingMessage(`Running ${algorithm === "cpp" ? "C++" : "Python"} solver…`)
        const world = await solve({ 
          warehouse: uploads.warehouse!, 
          obstacles: uploads.obstacles || "", 
          ceiling: uploads.ceiling!, 
          bays: uploads.bays!,
          algorithm 
        })
        if (cancelled) return

        const { polygon, obstacles, ceilingProfile, placedBays, bayTypes } = mapWorldToScene(world)
        console.log(`[WarehouseOS] ${placedBays.length} bays placed`)

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
    window.history.replaceState({}, "", "/warehouse")
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
        style={{ background: viewMode === "3d" ? "linear-gradient(to bottom, #76d0f5 0%, #f4f8fa 100%)" : "#f8fafc" }}
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
            viewMode={viewMode}
          />
        </div>

        {/* ── Splash title card ────────────────────────────────────────────── */}
        {splashPhase !== "hidden" && (
          <>
            <style>{`
              @keyframes splashWordIn {
                from { opacity: 0; transform: translateY(18px) scale(0.97); }
                to   { opacity: 1; transform: translateY(0)    scale(1);    }
              }
              @keyframes splashSubIn {
                from { opacity: 0; }
                to   { opacity: 1; }
              }
            `}</style>
            <div
              className="absolute inset-0 z-50 flex flex-col items-center justify-center gap-8"
              style={{
                background: "linear-gradient(160deg, #090b10 0%, #0e1420 55%, #0f1117 100%)",
                opacity: splashPhase === "fading" ? 0 : 1,
                transition: "opacity 0.7s cubic-bezier(0.4, 0, 0.2, 1)",
                pointerEvents: splashPhase === "fading" ? "none" : "auto",
              }}
            >
              <div style={{ textAlign: "center" }}>
                <h1
                  style={{
                    fontFamily: "'Inter', sans-serif",
                    fontSize: "clamp(3.5rem, 11vw, 9rem)",
                    fontWeight: 800,
                    letterSpacing: "-0.04em",
                    lineHeight: 1,
                    background: "linear-gradient(135deg, #ffffff 40%, rgba(165,180,252,0.85) 100%)",
                    WebkitBackgroundClip: "text",
                    WebkitTextFillColor: "transparent",
                    animation: "splashWordIn 0.65s cubic-bezier(0.22,1,0.36,1) both",
                  }}
                >
                  WarehouseOS
                </h1>
                {splashCase && (
                  <p
                    style={{
                      marginTop: "1.25rem",
                      color: "rgba(255,255,255,0.28)",
                      fontSize: "0.8rem",
                      letterSpacing: "0.22em",
                      textTransform: "uppercase",
                      fontFamily: "'Inter', sans-serif",
                      fontWeight: 500,
                      animation: "splashSubIn 0.5s 0.4s ease both",
                    }}
                  >
                    {splashCase}
                  </p>
                )}
              </div>

            </div>
          </>
        )}

        {/* ── Status chip + Exterior Controls (unified right panel) ─────────── */}
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
            {parsedData.placedBays.length} bays placed
          </div>

          {/* Exterior dropdown — directly below, no gap */}
          <div className="pointer-events-auto flex flex-col items-end">
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

        {/* ── Picture-in-Picture Mini-Map ─────────────────────────────────── */}
        <div 
          className="pointer-events-auto absolute bottom-6 right-6 z-30 h-48 w-48 overflow-hidden rounded-2xl border-4 shadow-2xl transition-transform hover:scale-105 active:scale-95 sm:h-64 sm:w-64"
          style={{ 
            borderColor: "white", 
            background: viewMode === "3d" ? "#f8fafc" : "linear-gradient(to bottom, #76d0f5 0%, #f4f8fa 100%)",
            boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.25)"
          }}
        >
          {/* We render a second tiny scene instance with the INVERTED viewMode */}
          <WarehouseScene
            polygon={parsedData.polygon}
            obstacles={parsedData.obstacles}
            ceilingProfile={parsedData.ceilingProfile}
            placedBays={parsedData.placedBays}
            introPhase="interactive" // Skip the camera intro animation!
            introStartMs={0}
            onIntroDone={() => {}}
            selectedBayId={null} // Don't highlight selections in the mini map
            onSelectBay={() => {}}
            onClearSelection={() => {}}
            exteriorMode={exteriorMode}
            viewMode={viewMode === "3d" ? "floor_plan" : "3d"}
            isMiniMap={true}
          />
          
          {/* Invisible interactive overlay to intercept all clicks and prevent orbit control panning */}
          <button
            className="absolute inset-0 h-full w-full cursor-pointer focus:outline-none"
            title={`Switch to ${viewMode === "3d" ? "Floor Plan" : "3D"} View`}
            onClick={(e) => {
              e.stopPropagation();
              setViewMode(v => v === "3d" ? "floor_plan" : "3d");
            }}
          />
        </div>
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

        {/* Algorithm Selection */}
        <div className="flex items-center justify-center gap-4">
          <span className="text-sm font-medium text-slate-700">Algorithm:</span>
          <div className="flex rounded bg-white/40 p-1 border" style={{ borderColor: "rgba(15,23,42,0.2)" }}>
            <button
              onClick={() => setAlgorithm("cpp")}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${algorithm === "cpp" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
            >
              C++ (Fast)
            </button>
            <button
              onClick={() => setAlgorithm("python")}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${algorithm === "python" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
            >
              Python
            </button>
          </div>
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
