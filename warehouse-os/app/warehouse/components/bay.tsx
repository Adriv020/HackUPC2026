"use client"

import { useState, useMemo } from "react"
import * as THREE from "three"
import type { PlacedBay } from "@/lib/warehouse-service"

type BayProps = {
  bay: PlacedBay
  isSelected: boolean
  onSelectBay: (bayId: string) => void
  viewMode?: "3d" | "floor_plan"
}

const CLICK_DELTA_THRESHOLD = 4

// Colours — warm industrial aesthetic, bright warehouse
const COLOR_UPRIGHT  = "#5a6470"  // charcoal steel posts
const COLOR_BEAM     = "#7a8898"  // mid steel beams
const COLOR_SHELF    = "#94a3b5"  // shelf surface board
const COLOR_SELECTED = "#2563eb"  // strong blue highlight
const COLOR_HOVER    = "#3b82f6"  // hover highlight

export function Bay({ bay, isSelected, onSelectBay, viewMode = "3d" }: BayProps) {
  const [hoveredLevel, setHoveredLevel] = useState<number | null>(null)

  const { width, depth, height } = bay
  const halfW = width / 2
  const halfD = depth / 2

  const nLoads = bay.bayTypeData.nLoads || 0

  // Box logic (1 unit = 100mm, so 5.0 = 500mm box)
  const BOX_SIZE = 5.0
  const usableW = width - 1.0
  const usableD = depth - 1.0
  
  const boxesPerRow = Math.max(1, Math.floor(usableW / BOX_SIZE))
  const rowsPerShelf = Math.max(1, Math.floor(usableD / BOX_SIZE))
  const capacityPerShelf = boxesPerRow * rowsPerShelf

  // Calculate shelves needed to fit all loads (minimum 1)
  const levels = Math.max(1, Math.ceil(nLoads / capacityPerShelf))

  // Upright post positions (4 corners relative to bay centre)
  const uprightPositions: [number, number, number][] = [
    [-halfW + 0.025, height / 2, -halfD + 0.025],
    [ halfW - 0.025, height / 2, -halfD + 0.025],
    [-halfW + 0.025, height / 2,  halfD - 0.025],
    [ halfW - 0.025, height / 2,  halfD - 0.025],
  ]

  // Shelf levels Y positions
  const levelYPositions = Array.from({ length: levels }, (_, i) => {
    return (i + 1) * (height / (levels + 1))
  })

  // Selection outline geometry
  const selectionGeo = useMemo(() => new THREE.EdgesGeometry(
    new THREE.BoxGeometry(width, height, depth)
  ), [width, height, depth])

  return (
    // Bay group is centred at its position (bottom-centre of footprint)
    // We offset Y by height/2 so the bottom of the bay is at y=0
    <group position={bay.position}>
      {/* Vertical upright posts at 4 corners */}
      {uprightPositions.map((pos, i) => (
        <mesh key={`post-${i}`} position={pos} castShadow>
          <boxGeometry args={[0.05, height, 0.05]} />
          <meshStandardMaterial color={COLOR_UPRIGHT} flatShading={true} roughness={0.7} />
        </mesh>
      ))}

      {/* Shelf levels — beams + surfaces */}
      {levelYPositions.map((levelY, li) => {
        const isHovered = hoveredLevel === li
        const surfaceColor = isSelected && isHovered
          ? COLOR_SELECTED
          : isHovered
            ? COLOR_HOVER
            : isSelected
              ? "#90cdf4"
              : COLOR_SHELF

        return (
          <group key={`level-${li}`} position={[0, levelY, 0]}>
            {/* Front beam — at near edge of bay */}
            <mesh position={[0, 0, -halfD + 0.025]} castShadow>
              <boxGeometry args={[width, 0.04, 0.05]} />
              <meshStandardMaterial color={COLOR_BEAM} flatShading={true} />
            </mesh>
            {/* Back beam — at far edge of bay */}
            <mesh position={[0, 0, halfD - 0.025]} castShadow>
              <boxGeometry args={[width, 0.04, 0.05]} />
              <meshStandardMaterial color={COLOR_BEAM} flatShading={true} />
            </mesh>

            {/* Shelf surface — this is the CLICKABLE mesh */}
            <mesh
              position={[0, 0.035, 0]}
              castShadow
              receiveShadow
              onPointerOver={(e) => {
                e.stopPropagation()
                setHoveredLevel(li)
                document.body.style.cursor = "pointer"
              }}
              onPointerOut={(e) => {
                e.stopPropagation()
                setHoveredLevel(null)
                document.body.style.cursor = "auto"
              }}
              onClick={(e) => {
                if (e.delta > CLICK_DELTA_THRESHOLD) return
                e.stopPropagation()
                onSelectBay(bay.id)
              }}
            >
              <boxGeometry args={[width - 0.1, 0.03, depth - 0.1]} />
              <meshStandardMaterial
                color={surfaceColor}
                flatShading={true}
                roughness={0.8}
              />
            </mesh>

            {/* Boxes on this shelf */}
            {viewMode === "3d" && Array.from({ length: Math.min(capacityPerShelf, Math.max(0, nLoads - li * capacityPerShelf)) }).map((_, boxIdx) => {
              const row = Math.floor(boxIdx / boxesPerRow)
              const col = boxIdx % boxesPerRow
              
              const totalW = boxesPerRow * BOX_SIZE
              const totalD = rowsPerShelf * BOX_SIZE
              const startX = -totalW / 2 + BOX_SIZE / 2
              const startZ = -totalD / 2 + BOX_SIZE / 2
              
              const bx = startX + col * BOX_SIZE
              const bz = startZ + row * BOX_SIZE
              const by = 0.05 + (BOX_SIZE * 0.95) / 2
              
              return (
                <group key={`box-${boxIdx}`} position={[bx, by, bz]}>
                  {/* Cardboard Box */}
                  <mesh castShadow receiveShadow>
                    <boxGeometry args={[BOX_SIZE * 0.95, BOX_SIZE * 0.95, BOX_SIZE * 0.95]} />
                    <meshStandardMaterial color="#cfa474" roughness={0.9} flatShading={true} />
                  </mesh>
                  {/* Blue Tape Stripe */}
                  <mesh position={[0, (BOX_SIZE * 0.95) / 2 + 0.002, 0]} castShadow>
                    <boxGeometry args={[BOX_SIZE * 0.95, 0.005, BOX_SIZE * 0.15]} />
                    <meshStandardMaterial color="#3b82f6" roughness={0.6} />
                  </mesh>
                  {/* White Label */}
                  <mesh position={[(BOX_SIZE * 0.95) / 2 + 0.002, 0, BOX_SIZE * 0.2]} castShadow>
                    <boxGeometry args={[0.005, BOX_SIZE * 0.2, BOX_SIZE * 0.25]} />
                    <meshStandardMaterial color="#ffffff" roughness={0.5} />
                  </mesh>
                </group>
              )
            })}
          </group>
        )
      })}

      {/* Selection outline — only visible when this bay is selected */}
      {isSelected && (
        <lineSegments geometry={selectionGeo} position={[0, height / 2, 0]}>
          <lineBasicMaterial color={COLOR_SELECTED} linewidth={2} />
        </lineSegments>
      )}
    </group>
  )
}
