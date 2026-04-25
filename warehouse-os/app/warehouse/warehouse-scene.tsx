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
import { EarthBackdrop } from "./components/earth-backdrop"

export type IntroPhase = "intro_orbit" | "interactive"

const INTRO_DURATION_MS = 5400

function easeOutQuint(t: number): number {
  return 1 - Math.pow(1 - t, 5)
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

function IntroCameraController({
  cx, cz, maxDim, introStartMs, onDone,
}: {
  cx: number; cz: number; maxDim: number; introStartMs: number; onDone: () => void
}) {
  const doneRef = useRef(false)
  useFrame(({ camera }) => {
    if (doneRef.current) return
    const elapsed = performance.now() - introStartMs
    const rawT = Math.min(elapsed / INTRO_DURATION_MS, 1)
    const easedT = easeOutQuint(rawT)
    const startX = cx + maxDim * 1.05
    const startY = maxDim * 1.15
    const startZ = cz - maxDim * 0.85
    const endX = cx + maxDim * 0.52
    const endY = maxDim * 0.52
    const endZ = cz + maxDim * 0.72
    const orbitFade = 1 - easedT
    const orbitAngle = orbitFade * Math.PI * 1.3
    const orbitR = maxDim * 0.3 * orbitFade
    camera.position.set(
      lerp(startX, endX, easedT) + Math.sin(orbitAngle) * orbitR,
      lerp(startY, endY, easedT),
      lerp(startZ, endZ, easedT) + Math.cos(orbitAngle) * orbitR,
    )
    camera.lookAt(cx, 0, cz)
    if (rawT >= 1) { doneRef.current = true; onDone() }
  })
  return null
}

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
  polygon, obstacles, ceilingProfile, placedBays,
  introPhase, introStartMs, onIntroDone,
  selectedBayId, onSelectBay, onClearSelection,
}: Props) {
  const bounds = useMemo(() => computeWarehouseBounds(polygon), [polygon])
  const [cx, cz] = useMemo(() => computeWarehouseCentroid(polygon), [polygon])
  const maxDim = Math.max(bounds.width, bounds.depth)

  const initPos: [number, number, number] = [
    cx + maxDim * 1.05,
    maxDim * 1.15,
    cz - maxDim * 0.85,
  ]

  const handleDone = useCallback(() => { onIntroDone() }, [onIntroDone])

  // Sunlight comes from upper-front-right — warm golden angle
  const sunPos: [number, number, number] = [
    cx + maxDim * 0.6,
    maxDim * 1.4,
    cz + maxDim * 0.4,
  ]
  // Fill light from the sky — cool blue from opposite side
  const skyFillPos: [number, number, number] = [
    cx - maxDim * 0.5,
    maxDim * 0.8,
    cz - maxDim * 0.3,
  ]

  return (
    <Canvas
      camera={{ position: initPos, fov: 45, near: 0.1, far: 3000 }}
      shadows
      dpr={[1, 1.5]}
      gl={{ antialias: true, powerPreference: "high-performance" }}
      onPointerMissed={onClearSelection}
    >
      {/* Bright sky blue background */}
      <color attach="background" args={["#c8e6f5"]} />
      {/* Very light haze — barely-there, keeps depth without darkening */}
      <fog attach="fog" args={["#daeef8", maxDim * 6, maxDim * 20]} />

      {/* ── Sunny warehouse lighting ────────────────────────────────────── */}
      {/* Bright sky ambient — fills everything with cool blue-white light */}
      <ambientLight intensity={0.75} color="#d6eeff" />

      {/* Primary sun — warm golden directional, strong */}
      <directionalLight
        position={sunPos}
        intensity={2.2}
        color="#ffe9b0"
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-left={-maxDim * 1.4}
        shadow-camera-right={maxDim * 1.4}
        shadow-camera-top={maxDim * 1.4}
        shadow-camera-bottom={-maxDim * 1.4}
        shadow-camera-near={1}
        shadow-camera-far={500}
      />

      {/* Sky fill — cool blue from opposite angle, mimics skylight through windows */}
      <directionalLight
        position={skyFillPos}
        intensity={0.6}
        color="#a8d8f0"
      />

      {/* Hemisphere — warm concrete ground bounce + cool sky top */}
      <hemisphereLight
        args={["#b8d9ef", "#c8b89a", 0.5]}
      />

      {/* ── Scene geometry ────────────────────────────────────────────────── */}
      <EarthBackdrop
        centerX={cx}
        centerZ={cz}
        floorWidth={bounds.width}
        floorDepth={bounds.depth}
      />
      <WarehouseShell polygon={polygon} ceilingProfile={ceilingProfile} />
      <ObstacleGroup obstacles={obstacles} ceilingProfile={ceilingProfile} />
      <CeilingShell polygon={polygon} ceilingProfile={ceilingProfile} />
      <BayGroup
        placedBays={placedBays}
        selectedBayId={selectedBayId}
        onSelectBay={onSelectBay}
      />

      {introPhase === "intro_orbit" && (
        <IntroCameraController
          cx={cx} cz={cz} maxDim={maxDim}
          introStartMs={introStartMs} onDone={handleDone}
        />
      )}

      <OrbitControls
        enabled={introPhase === "interactive"}
        enableDamping
        dampingFactor={0.08}
        target={[cx, 0, cz]}
        minDistance={10}
        maxDistance={500}
        maxPolarAngle={Math.PI / 2.1}
        mouseButtons={{ LEFT: MOUSE.ROTATE, MIDDLE: MOUSE.DOLLY, RIGHT: MOUSE.PAN }}
      />
    </Canvas>
  )
}
