"use client"

import { useRef, useMemo, useCallback } from "react"
import { Canvas, useFrame } from "@react-three/fiber"
import { OrbitControls } from "@react-three/drei"
import { MOUSE } from "three"
import {
  computeWarehouseBounds,
  computeWarehouseCentroid,
  type CeilingProfile,
  type ObstacleConfig,
  type PlacedBay,
  type WarehousePolygon,
} from "@/lib/warehouse-service"
import { WarehouseShell } from "./components/warehouse-shell"
import { ObstacleGroup } from "./components/obstacle-group"
import { CeilingShell } from "./components/ceiling-shell"
import { BayGroup } from "./components/bay-group"

export type IntroPhase = "intro_orbit" | "interactive"

// Duration of the orbital camera intro animation (mirrors Gaia's ~5600 ms)
const INTRO_DURATION_MS = 5400

function easeOutQuint(t: number): number {
  return 1 - Math.pow(1 - t, 5)
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

// ─── Intro camera ─────────────────────────────────────────────────────────────
// Runs useFrame while introPhase === "intro_orbit".  Orbits around the centroid
// while smoothly descending from a bird's-eye position into the interactive
// 3/4-view position, then calls onDone() to hand off to OrbitControls.
function IntroCameraController({
  cx, cz, maxDim, introStartMs, onDone,
}: {
  cx: number
  cz: number
  maxDim: number
  introStartMs: number
  onDone: () => void
}) {
  const doneRef = useRef(false)

  useFrame(({ camera }) => {
    if (doneRef.current) return

    const elapsed = performance.now() - introStartMs
    const rawT = Math.min(elapsed / INTRO_DURATION_MS, 1)
    const easedT = easeOutQuint(rawT)

    // Start: high bird's-eye, far corner
    const startX = cx + maxDim * 1.05
    const startY = maxDim * 1.15
    const startZ = cz - maxDim * 0.85

    // End: comfortable 45° 3/4 view
    const endX = cx + maxDim * 0.52
    const endY = maxDim * 0.52
    const endZ = cz + maxDim * 0.72

    // Orbital swing that decays to zero as easedT → 1
    const orbitFade = 1 - easedT
    const orbitAngle = orbitFade * Math.PI * 1.3
    const orbitR = maxDim * 0.3 * orbitFade

    camera.position.set(
      lerp(startX, endX, easedT) + Math.sin(orbitAngle) * orbitR,
      lerp(startY, endY, easedT),
      lerp(startZ, endZ, easedT) + Math.cos(orbitAngle) * orbitR,
    )
    camera.lookAt(cx, 0, cz)

    if (rawT >= 1) {
      doneRef.current = true
      onDone()
    }
  })

  return null
}

// ─── Scene ────────────────────────────────────────────────────────────────────

type Props = {
  polygon: WarehousePolygon
  obstacles: ObstacleConfig[]
  ceilingProfile: CeilingProfile
  placedBays: PlacedBay[]
  introPhase: IntroPhase
  introStartMs: number
  onIntroDone: () => void
  selectedBayId: string | null
  onSelectBay: (bayId: string) => void
  onClearSelection: () => void
}

export function WarehouseScene({
  polygon,
  obstacles,
  ceilingProfile,
  placedBays,
  introPhase,
  introStartMs,
  onIntroDone,
  selectedBayId,
  onSelectBay,
  onClearSelection,
}: Props) {
  const bounds = useMemo(() => computeWarehouseBounds(polygon), [polygon])
  const [cx, cz] = useMemo(() => computeWarehouseCentroid(polygon), [polygon])
  const maxDim = Math.max(bounds.width, bounds.depth)

  // Camera starts at the same position the intro animation begins from
  const initPos: [number, number, number] = [
    cx + maxDim * 1.05,
    maxDim * 1.15,
    cz - maxDim * 0.85,
  ]

  const handleDone = useCallback(() => {
    onIntroDone()
  }, [onIntroDone])

  // Second directional light position — opposite-front corner for rim light
  const rimLightPos: [number, number, number] = [
    cx - maxDim * 0.8,
    maxDim * 0.6,
    cz + maxDim * 0.6,
  ]

  return (
    <Canvas
      camera={{ position: initPos, fov: 45, near: 0.1, far: 3000 }}
      shadows
      dpr={[1, 1.5]}
      gl={{ antialias: true, powerPreference: "high-performance" }}
      onPointerMissed={onClearSelection}
    >
      {/* BUG 3: Dark navy background — makes pale walls and blue ceiling pop */}
      <color attach="background" args={["#1a202c"]} />
      {/* BUG 3: Fog for depth — copy Gaia's fog pattern */}
      <fog attach="fog" args={["#1a202c", 80, 400]} />

      {/* ── Lighting — BUG 3 fix ─────────────────────────────────────────────── */}
      {/* Ambient: brighter, warm white — flat shading needs more ambient */}
      <ambientLight intensity={0.6} color="#f7fafc" />

      {/* Primary directional — casts shadows */}
      <directionalLight
        position={[cx + 50, 80, cz + 50]}
        intensity={0.8}
        color="#ffffff"
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-left={-maxDim * 1.2}
        shadow-camera-right={maxDim * 1.2}
        shadow-camera-top={maxDim * 1.2}
        shadow-camera-bottom={-maxDim * 1.2}
        shadow-camera-near={1}
        shadow-camera-far={400}
      />

      {/* BUG 3: Second directional — cool rim light from opposite-front corner */}
      <directionalLight
        position={rimLightPos}
        intensity={0.4}
        color="#bee3f8"
      />

      {/* BUG 3: Hemisphere light — makes flat-shaded low poly look great */}
      <hemisphereLight
        args={["#ebf8ff", "#4a5568", 0.3]}
      />

      {/* ── Scene geometry ──────────────────────────────────────────────────── */}
      <WarehouseShell polygon={polygon} ceilingProfile={ceilingProfile} />
      <ObstacleGroup obstacles={obstacles} ceilingProfile={ceilingProfile} />
      <CeilingShell polygon={polygon} ceilingProfile={ceilingProfile} />
      <BayGroup
        placedBays={placedBays}
        selectedBayId={selectedBayId}
        onSelectBay={onSelectBay}
      />

      {/* ── Intro camera animation ──────────────────────────────────────────── */}
      {introPhase === "intro_orbit" && (
        <IntroCameraController
          cx={cx}
          cz={cz}
          maxDim={maxDim}
          introStartMs={introStartMs}
          onDone={handleDone}
        />
      )}

      {/* ── Orbit controls — enabled only after intro finishes ──────────────── */}
      <OrbitControls
        enabled={introPhase === "interactive"}
        enableDamping
        dampingFactor={0.08}
        target={[cx, 0, cz]}
        minDistance={10}
        maxDistance={500}
        maxPolarAngle={Math.PI / 2.1}
        mouseButtons={{
          LEFT: MOUSE.ROTATE,
          MIDDLE: MOUSE.DOLLY,
          RIGHT: MOUSE.PAN,
        }}
      />
    </Canvas>
  )
}
