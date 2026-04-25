"use client"

import { useMemo } from "react"
import * as THREE from "three"
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

const WALL_THICKNESS = 0.2
const FLOOR_DEPTH = 0.2

export function WarehouseShell({ polygon, ceilingProfile }: Props) {
  const { points } = polygon
  const bounds = useMemo(() => computeWarehouseBounds(polygon), [polygon])

  // Floor: ExtrudeGeometry from the warehouse polygon, lying flat in XZ plane.
  // BUG 1 FIX: Coordinate mapping — CSV coordX → Three.js X, CSV coordY → Three.js Z (negated).
  // Points are already stored as { x: csvX/100, z: -csvY/100 }.
  // Shape is built in 2D with (p.x, p.z) — then rotateX(-PI/2) maps:
  //   shape (x, y=z_value, z=0) → world (x, 0, -z_value) = (x, 0, p.z is already negative)
  // Using shape.moveTo(p.x, p.z) and then rotateX(-PI/2) lands at (p.x, 0, -p.z) = wrong sign
  // So we use shape.moveTo(p.x, -p.z) to counteract: world Z = -(-p.z) = p.z ✓
  const floorGeo = useMemo(() => {
    const shape = new THREE.Shape()
    shape.moveTo(points[0].x, -points[0].z)
    for (let i = 1; i < points.length; i++) {
      shape.lineTo(points[i].x, -points[i].z)
    }
    shape.closePath()
    const geo = new THREE.ExtrudeGeometry(shape, {
      depth: FLOOR_DEPTH,
      bevelEnabled: false,
    })
    geo.rotateX(-Math.PI / 2)
    geo.translate(0, -FLOOR_DEPTH, 0)
    return geo
  }, [points])

  // Grid helper dimensions based on warehouse bounds
  const gridSize = useMemo(() => {
    return Math.max(bounds.width, bounds.depth) * 1.2
  }, [bounds])

  const gridCenter = useMemo(() => {
    return [(bounds.minX + bounds.maxX) / 2, (bounds.minZ + bounds.maxZ) / 2] as [number, number]
  }, [bounds])

  // Walls: one BoxGeometry per polygon edge, correctly positioned and rotated.
  // BUG 1 FIX: Walls use p.x and p.z (already in Three.js coords). Wall midpoint
  // and rotation computed with corrected Z values.
  const walls = useMemo(() => {
    return points.map((p1, i) => {
      const p2 = points[(i + 1) % points.length]
      const dx = p2.x - p1.x
      const dz = p2.z - p1.z
      const len = Math.sqrt(dx * dx + dz * dz)
      if (len < 0.001) return null
      const midX = (p1.x + p2.x) / 2
      const midZ = (p1.z + p2.z) / 2
      // getCeilingHeight uses the midpoint X of each wall segment
      const wallHeight = getCeilingHeight(ceilingProfile, midX)
      // BUG 1 FIX: rotation.y = -atan2(z2-z1, x2-x1) aligns box X axis with edge direction
      const rotY = -Math.atan2(dz, dx)
      return { len, midX, midZ, wallHeight, rotY, key: `wall-${i}` }
    }).filter((w): w is NonNullable<typeof w> => w !== null)
  }, [points, ceilingProfile])

  return (
    <group>
      {/* Floor — BUG 3: dark blue-grey concrete colour with flat shading */}
      <mesh geometry={floorGeo} receiveShadow>
        <meshStandardMaterial
          color="#4a5568"
          roughness={0.9}
          metalness={0.02}
          flatShading={true}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* Floor grid — industrial tile feel */}
      <gridHelper
        args={[gridSize, 20, "#718096", "#718096"]}
        position={[gridCenter[0], 0.01, gridCenter[1]]}
      />

      {/* Walls — BUG 3: light grey-blue, transparent, with edge outlines */}
      {walls.map(w => {
        const wallGeo = new THREE.BoxGeometry(w.len, w.wallHeight, WALL_THICKNESS)
        const edgesGeo = new THREE.EdgesGeometry(wallGeo)
        return (
          <group
            key={w.key}
            position={[w.midX, w.wallHeight / 2, w.midZ]}
            rotation={[0, w.rotY, 0]}
          >
            <mesh castShadow receiveShadow>
              <boxGeometry args={[w.len, w.wallHeight, WALL_THICKNESS]} />
              <meshStandardMaterial
                color="#cbd5e0"
                transparent
                opacity={0.35}
                flatShading={true}
                side={THREE.DoubleSide}
                depthWrite={false}
              />
            </mesh>
            <lineSegments geometry={edgesGeo}>
              <lineBasicMaterial color="#a0aec0" linewidth={1} transparent opacity={0.6} />
            </lineSegments>
          </group>
        )
      })}
    </group>
  )
}
