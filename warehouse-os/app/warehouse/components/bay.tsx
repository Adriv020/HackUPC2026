"use client"

import { useState, useMemo } from "react"
import * as THREE from "three"
import type { PlacedBay } from "@/lib/warehouse-service"

type BayProps = {
  bay: PlacedBay
  isSelected: boolean
  onSelectBay: (bayId: string) => void
}

const CLICK_DELTA_THRESHOLD = 4

// Colours — low-poly game aesthetic
const COLOR_UPRIGHT  = "#2d3748"  // dark steel posts
const COLOR_BEAM     = "#4a5568"  // medium steel beams
const COLOR_SHELF    = "#718096"  // shelf surface board
const COLOR_SELECTED = "#63b3ed"  // selection blue highlight
const COLOR_HOVER    = "#63b3ed"  // hover highlight

export function Bay({ bay, isSelected, onSelectBay }: BayProps) {
  const [hoveredLevel, setHoveredLevel] = useState<number | null>(null)

  const { width, depth, height } = bay
  const halfW = width / 2
  const halfD = depth / 2

  // Number of shelf levels
  const levels = Math.max(1, Math.floor(height / 0.8))

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
