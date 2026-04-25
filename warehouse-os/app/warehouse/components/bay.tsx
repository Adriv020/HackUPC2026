"use client"

import { useState, useMemo } from "react"
import * as THREE from "three"
import { useTexture } from "@react-three/drei"
import type { PlacedBay } from "@/lib/warehouse-service"

type BayProps = {
  bay: PlacedBay
  isSelected: boolean
  onSelectBay: (bayId: string) => void
  viewMode?: "3d" | "floor_plan"
}

const CLICK_DELTA_THRESHOLD = 4

// Colours — Mecalux brand palette
const COLOR_UPRIGHT  = "#1a2d5e"  // Mecalux dark navy blue uprights
const COLOR_BEAM     = "#e8621a"  // Mecalux vivid orange beams
const COLOR_SHELF    = "#d45a18"  // slightly deeper orange shelf surface
const COLOR_SELECTED = "#f97316"  // bright orange-amber highlight
const COLOR_HOVER    = "#fb923c"  // lighter orange hover

export function Bay({ bay, isSelected, onSelectBay, viewMode = "3d" }: BayProps) {
  const [hoveredLevel, setHoveredLevel] = useState<number | null>(null)
  const logoTexture = useTexture("/Mecalux.jpg")

  // Make texture look crisp on the small label
  logoTexture.colorSpace = THREE.SRGBColorSpace

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
    // Bay group is centred at its geometric center in the world
    // We offset Y by height/2 so the bottom of the bay is at y=0
    // We apply true rotation around the Y axis (negative because Three.js Y is "up" while 2D Y was "down" relative to Z)
    <group 
      position={bay.position} 
      rotation={[0, -(bay.rotation || 0) * Math.PI / 180, 0]}
    >
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
                  {/* Mecalux logo — JPG with white background, applied directly to box face */}
                  {/* polygonOffset pushes this plane forward in depth-buffer space, eliminating z-fighting */}
                  <mesh
                    position={[(BOX_SIZE * 0.95) / 2 + 0.001, 0, BOX_SIZE * 0.1]}
                    rotation={[0, Math.PI / 2, 0]}
                  >
                    <planeGeometry args={[BOX_SIZE * 0.35, BOX_SIZE * 0.35]} />
                    <meshStandardMaterial
                      map={logoTexture}
                      roughness={0.4}
                      polygonOffset={true}
                      polygonOffsetFactor={-1}
                      polygonOffsetUnits={-1}
                    />
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
