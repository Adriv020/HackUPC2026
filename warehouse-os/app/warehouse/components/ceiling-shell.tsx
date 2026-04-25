"use client"

import { useMemo, useRef } from "react"
import * as THREE from "three"
import { useFrame } from "@react-three/fiber"
import {
  clipPolygonToXStrip,
  computeWarehouseBounds,
  type CeilingProfile,
  type Point2D,
  type WarehousePolygon,
} from "@/lib/warehouse-service"

type Props = {
  polygon: WarehousePolygon
  ceilingProfile: CeilingProfile
}

// BUG 2 FIX: Completely rebuilt ceiling using Sutherland-Hodgman polygon clipping.
// Each ceiling segment clips the warehouse polygon to the X strip [xStart, xEnd],
// then builds an ExtrudeGeometry slab positioned at the segment ceiling height.

function buildCeilingPanelGeo(clippedPoly: Point2D[], thickness: number): THREE.BufferGeometry {
  // Build a THREE.Shape from the clipped polygon.
  // The polygon is in Three.js XZ space. Shape is built in XZ (2D: x → shapeX, z → shapeY).
  // ExtrudeGeometry extrudes along Z by default.
  // We rotate -PI/2 around X to make it lie flat in XZ (horizontal slab).
  const shape = new THREE.Shape()
  shape.moveTo(clippedPoly[0].x, -clippedPoly[0].z)
  for (let i = 1; i < clippedPoly.length; i++) {
    shape.lineTo(clippedPoly[i].x, -clippedPoly[i].z)
  }
  shape.closePath()

  const geo = new THREE.ExtrudeGeometry(shape, {
    depth: thickness,
    bevelEnabled: false,
  })
  // Rotate so the extruded shape lies flat (extrusion was along Z, now along Y)
  geo.rotateX(-Math.PI / 2)
  return geo
}

const PANEL_THICKNESS = 0.1

export function CeilingShell({ polygon, ceilingProfile }: Props) {
  const { points } = polygon
  const bounds = useMemo(() => computeWarehouseBounds(polygon), [polygon])
  const gridCenter = useMemo(
    () => [(bounds.minX + bounds.maxX) / 2, (bounds.minZ + bounds.maxZ) / 2] as [number, number],
    [bounds]
  )
  const { segments } = ceilingProfile

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

  // Generate a procedural ribbed texture for the roof slats
  const roofTexture = useMemo(() => {
    const canvas = document.createElement("canvas")
    canvas.width = 128
    canvas.height = 128
    const context = canvas.getContext("2d")
    if (context) {
      context.fillStyle = "#6e7f9c" // Base blue/grey
      context.fillRect(0, 0, 128, 128)
      context.fillStyle = "#5c6b87" // Darker slat line
      context.fillRect(0, 110, 128, 18)
    }
    const tex = new THREE.CanvasTexture(canvas)
    tex.wrapS = THREE.RepeatWrapping
    tex.wrapT = THREE.RepeatWrapping
    // Repeat more on the Z axis to create horizontal slats
    tex.repeat.set(1, Math.max(bounds.depth / 2, 5))
    return tex
  }, [bounds])

  const panels = useMemo(() => {
    if (segments.length === 0) return []

    // Build segment X ranges: each consecutive pair is a ceiling segment.
    // The final X breakpoint extends to the max X extent of the warehouse polygon.
    const result: Array<{
      key: string
      clippedPoly: Point2D[]
      height: number
    }> = []

    // Handle single segment case: clip to entire polygon X extent
    if (segments.length === 1) {
      const clipped = clipPolygonToXStrip(points, bounds.minX, bounds.maxX)
      if (clipped.length >= 3) {
        result.push({ key: 'ceil-0', clippedPoly: clipped, height: segments[0].height })
      }
      return result
    }

    for (let i = 0; i < segments.length - 1; i++) {
      const seg = segments[i]
      const next = segments[i + 1]
      const xStart = seg.x
      const xEnd = next.x
      // TODO: slope/lerp between seg.height and next.height is a future enhancement.
      // For now, use the START height of the segment (flat panel).
      const height = seg.height

      const clipped = clipPolygonToXStrip(points, xStart, xEnd)
      if (clipped.length >= 3) {
        result.push({ key: `ceil-${i}`, clippedPoly: clipped, height })
      }
    }

    // Final segment: last breakpoint X to polygon maxX
    const lastSeg = segments[segments.length - 1]
    if (lastSeg.x < bounds.maxX) {
      const clipped = clipPolygonToXStrip(points, lastSeg.x, bounds.maxX)
      if (clipped.length >= 3) {
        result.push({ key: `ceil-last`, clippedPoly: clipped, height: lastSeg.height })
      }
    }

    return result
  }, [segments, points, bounds])

  return (
    <group>
      {panels.map(panel => {
        const geo = buildCeilingPanelGeo(panel.clippedPoly, PANEL_THICKNESS)
        const edgesGeo = new THREE.EdgesGeometry(geo)
        return (
          <group key={panel.key} position={[0, panel.height, 0]}>
            {/* Opaque procedural ribbed roof panel */}
            <mesh geometry={geo} castShadow receiveShadow>
              <meshStandardMaterial
                ref={registerMaterial}
                map={roofTexture}
                color="#ffffff" // Texture provides the color
                transparent
                opacity={1}
                roughness={0.9}
                side={THREE.DoubleSide}
              />
            </mesh>
            {/* Roof edge trim */}
            <lineSegments geometry={edgesGeo}>
              <lineBasicMaterial color="#3d4960" linewidth={2} transparent opacity={1} />
            </lineSegments>
          </group>
        )
      })}
    </group>
  )
}
