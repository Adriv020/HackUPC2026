"use client"

import { useMemo, useRef } from "react"
import * as THREE from "three"
import { useFrame } from "@react-three/fiber"
import {
  getCeilingHeight,
  type CeilingProfile,
  type WarehousePolygon,
  computeWarehouseBounds,
} from "@/lib/warehouse-service"

type Props = {
  polygon: WarehousePolygon
  ceilingProfile: CeilingProfile
}

const WALL_THICKNESS = 0.25
const FLOOR_DEPTH = 0.2

export function WarehouseShell({ polygon, ceilingProfile }: Props) {
  const { points } = polygon
  const bounds = useMemo(() => computeWarehouseBounds(polygon), [polygon])

  // Floor: ExtrudeGeometry from the warehouse polygon, lying flat in XZ.
  // Shape uses (p.x, -p.z) so that after rotateX(-PI/2) vertices land at (p.x, 0, p.z).
  const floorGeo = useMemo(() => {
    const shape = new THREE.Shape()
    shape.moveTo(points[0].x, -points[0].z)
    for (let i = 1; i < points.length; i++) {
      shape.lineTo(points[i].x, -points[i].z)
    }
    shape.closePath()
    const geo = new THREE.ExtrudeGeometry(shape, { depth: FLOOR_DEPTH, bevelEnabled: false })
    geo.rotateX(-Math.PI / 2)
    geo.translate(0, -FLOOR_DEPTH, 0)
    return geo
  }, [points])

  const gridSize = useMemo(() => Math.max(bounds.width, bounds.depth) * 1.4, [bounds])
  const gridCenter = useMemo(
    () => [(bounds.minX + bounds.maxX) / 2, (bounds.minZ + bounds.maxZ) / 2] as [number, number],
    [bounds]
  )

  // Walls: one BoxGeometry per polygon edge
  const walls = useMemo(() => {
    return points.map((p1, i) => {
      const p2 = points[(i + 1) % points.length]
      const dx = p2.x - p1.x
      const dz = p2.z - p1.z
      const len = Math.sqrt(dx * dx + dz * dz)
      if (len < 0.001) return null
      const midX = (p1.x + p2.x) / 2
      const midZ = (p1.z + p2.z) / 2
      const wallHeight = getCeilingHeight(ceilingProfile, midX)
      const rotY = -Math.atan2(dz, dx)
      return { len, midX, midZ, wallHeight, rotY, key: `wall-${i}` }
    }).filter((w): w is NonNullable<typeof w> => w !== null)
  }, [points, ceilingProfile])

  const materialRefs = useRef<THREE.MeshStandardMaterial[]>([])
  const fadeValueRef = useRef(1)
  const focusPointRef = useRef(new THREE.Vector3())

  const registerMaterial = (material: THREE.MeshStandardMaterial | null) => {
    if (!material) return
    if (materialRefs.current.includes(material)) return
    materialRefs.current.push(material)
  }

  useFrame(({ camera }, delta) => {
    const focus = focusPointRef.current
    focus.set(gridCenter[0], 2, gridCenter[1])
    const distance = camera.position.distanceTo(focus)
    
    // Fade out when zooming close to the center
    const maxDim = Math.max(bounds.width, bounds.depth)
    const nearHideDistance = maxDim * 0.45
    const farShowDistance = nearHideDistance + 10
    
    const targetFade = Math.max(0, Math.min(1, (distance - nearHideDistance) / (farShowDistance - nearHideDistance)))
    const smoothFactor = Math.max(0, Math.min(1, delta * 4.8))
    fadeValueRef.current += (targetFade - fadeValueRef.current) * smoothFactor
    
    const opacity = Math.pow(fadeValueRef.current, 1.1)
    const depthWrite = opacity > 0.96
    
    for (const material of materialRefs.current) {
      material.opacity = opacity
      material.depthWrite = depthWrite
    }
  })

  return (
    <group>
      {/* Floor — light warm concrete, like polished warehouse slab */}
      <mesh geometry={floorGeo} receiveShadow>
        <meshStandardMaterial
          color="#c4bfb8"
          roughness={0.85}
          metalness={0.02}
          flatShading={false}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* Subtle grid — very faint tile lines */}
      <gridHelper
        args={[gridSize, 20, "#a09890", "#a09890"]}
        position={[gridCenter[0], 0.01, gridCenter[1]]}
      />

      {/* Walls — Two-tone solid colours with windows */}
      {walls.map(w => {
        const baseTrimHeight = 1.2
        const mainWallHeight = Math.max(0, w.wallHeight - baseTrimHeight)
        
        // Procedural Windows
        const hasWindows = w.len > 6
        const windowWidth = 2.4
        const windowHeight = 1.2
        const numWindows = hasWindows ? Math.floor(w.len / 4.5) : 0
        const windowSpacing = w.len / (numWindows + 1)

        return (
          <group
            key={w.key}
            position={[w.midX, 0, w.midZ]}
            rotation={[0, w.rotY, 0]}
          >
            {/* Base Trim */}
            <mesh position={[0, baseTrimHeight / 2, 0]} castShadow receiveShadow>
              <boxGeometry args={[w.len, baseTrimHeight, WALL_THICKNESS + 0.05]} />
              <meshStandardMaterial
                ref={registerMaterial}
                color="#8c929a"
                roughness={0.9}
                transparent
                opacity={1}
                side={THREE.DoubleSide}
              />
            </mesh>
            
            {/* Main Upper Wall */}
            <mesh position={[0, baseTrimHeight + mainWallHeight / 2, 0]} castShadow receiveShadow>
              <boxGeometry args={[w.len, mainWallHeight, WALL_THICKNESS]} />
              <meshStandardMaterial
                ref={registerMaterial}
                color="#eef0f2"
                roughness={0.8}
                transparent
                opacity={1}
                side={THREE.DoubleSide}
              />
            </mesh>

            {/* Windows */}
            {hasWindows && Array.from({ length: numWindows }).map((_, idx) => {
              const winX = -w.len / 2 + (idx + 1) * windowSpacing
              const winY = baseTrimHeight + mainWallHeight * 0.45
              return (
                <group key={`win-${idx}`} position={[winX, winY, 0]}>
                  {/* Window Frame */}
                  <mesh>
                    <boxGeometry args={[windowWidth + 0.2, windowHeight + 0.2, WALL_THICKNESS + 0.1]} />
                    <meshStandardMaterial
                      ref={registerMaterial}
                      color="#6c788c"
                      roughness={0.6}
                      transparent
                      opacity={1}
                    />
                  </mesh>
                  {/* Glass Pane */}
                  <mesh>
                    <boxGeometry args={[windowWidth, windowHeight, WALL_THICKNESS + 0.12]} />
                    <meshStandardMaterial
                      ref={registerMaterial}
                      color="#98c5e8"
                      roughness={0.2}
                      metalness={0.5}
                      transparent
                      opacity={1}
                    />
                  </mesh>
                </group>
              )
            })}
          </group>
        )
      })}
    </group>
  )
}
