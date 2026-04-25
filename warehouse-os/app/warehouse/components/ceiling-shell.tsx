"use client"

import { useMemo } from "react"
import * as THREE from "three"
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
  const { segments } = ceilingProfile

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
            {/* Warm near-white ceiling slab — barely visible, lets sunlight feel right */}
            <mesh geometry={geo}>
              <meshStandardMaterial
                color="#e8e2d8"
                transparent
                opacity={0.25}
                roughness={0.8}
                flatShading={false}
                side={THREE.DoubleSide}
                depthWrite={false}
              />
            </mesh>
            {/* Structural edge lines on ceiling */}
            <lineSegments geometry={edgesGeo}>
              <lineBasicMaterial color="#b0a898" linewidth={1} transparent opacity={0.4} />
            </lineSegments>
          </group>
        )
      })}
    </group>
  )
}
