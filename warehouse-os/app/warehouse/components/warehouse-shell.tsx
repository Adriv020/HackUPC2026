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

      {/* Walls — light grey concrete, semi-transparent, warm tint */}
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
                color="#c8c4be"
                transparent
                opacity={0.55}
                roughness={0.9}
                metalness={0.0}
                flatShading={false}
                side={THREE.DoubleSide}
                depthWrite={false}
              />
            </mesh>
            {/* Structural edge lines */}
            <lineSegments geometry={edgesGeo}>
              <lineBasicMaterial color="#9a9590" linewidth={1} transparent opacity={0.5} />
            </lineSegments>
          </group>
        )
      })}
    </group>
  )
}
