// All CSV values are in millimetres. Scale factor converts to Three.js units.
const SCALE = 1 / 100

// ─── Types ────────────────────────────────────────────────────────────────────

export type Point2D = {
  x: number // Three.js X (scaled from CSV coordX)
  z: number // Three.js Z = -(CSV coordY * SCALE) — negative so Y increases INTO screen
}

export type WarehousePolygon = {
  points: Point2D[]
}

export type ObstacleConfig = {
  x: number     // corner x in Three.js units  (CSV coordX * SCALE)
  z: number     // corner z in Three.js units  (-CSV coordY * SCALE)
  width: number // extent along X axis
  depth: number // extent along Z axis
}

export type CeilingSegment = {
  x: number      // X breakpoint in Three.js units
  height: number // ceiling height in Three.js units
}

export type CeilingProfile = {
  segments: CeilingSegment[] // sorted ascending by x
}

export type WarehouseBounds = {
  minX: number
  maxX: number
  minZ: number
  maxZ: number
  width: number
  depth: number
}

// ─── Bay types ────────────────────────────────────────────────────────────────

export type BayTypeConfig = {
  typeId: string
  width: number  // Three.js units (mm / 100)
  depth: number  // Three.js units
  height: number // Three.js units (capped to ceiling - 0.3 at placement time)
  col4: string   // TODO: pending column definition — appears to be a load category label
  count: number  // number of bays of this type to place
  col6: string   // TODO: pending column definition — appears to be a priority/tier number
}

export type PlacedBay = {
  id: string
  typeId: string
  position: [number, number, number] // Three.js [x, 0, z] — bottom-centre of bay footprint
  width: number
  depth: number
  height: number
  bayTypeData: BayTypeConfig
}

// ─── Internal helpers ─────────────────────────────────────────────────────────

// Splits a CSV string into arrays of trimmed string tokens.
// Rows where the first token cannot be parsed as a number are silently skipped
// (handles optional header rows such as "coordX, coordY").
function parseNumericRows(csv: string): number[][] {
  return csv
    .split('\n')
    .map(line => line.split(',').map(s => s.trim()))
    .filter(parts => parts.length >= 1 && parts[0] !== '' && !isNaN(Number(parts[0])))
    .map(parts => parts.map(Number))
}

// Parse rows but keep first token as a string (for type_id which may be alpha)
function parseMixedRows(csv: string): string[][] {
  return csv
    .split('\n')
    .map(line => line.split(',').map(s => s.trim()))
    .filter(parts => parts.length >= 1 && parts[0] !== '')
    // Skip pure header rows where 2nd col is non-numeric string like "width_mm"
    .filter(parts => !['width_mm', 'width', 'coordx'].includes(parts[0].toLowerCase()))
}

// ─── Parsers ──────────────────────────────────────────────────────────────────

/**
 * Parse warehouse.csv — ordered polygon corner coordinates.
 * Each row: coordX, coordY
 * Maps: CSV coordX → Three.js X, CSV coordY → Three.js Z (negated).
 * Negation preserves correct winding order for ExtrudeGeometry shapes.
 */
export function parseWarehouseCSV(csv: string): WarehousePolygon {
  const rows = parseNumericRows(csv)
  const points: Point2D[] = rows
    .filter(r => r.length >= 2 && !r.some(isNaN))
    .map(r => ({ x: r[0] * SCALE, z: -(r[1] * SCALE) }))
  return { points }
}

/**
 * Parse obstacles.csv — axis-aligned boxes inside the warehouse.
 * Each row: coordX, coordY, width, depth
 * coordX/coordY is the CORNER of the obstacle (not centre).
 * Z is negated to match warehouse polygon coordinate convention.
 */
export function parseObstaclesCSV(csv: string): ObstacleConfig[] {
  if (!csv.trim()) return []
  const rows = parseNumericRows(csv)
  return rows
    .filter(r => r.length >= 4 && !r.some(isNaN))
    .map(r => ({
      x:     r[0] * SCALE,
      z:     -(r[1] * SCALE),   // negate to match warehouse polygon mapping
      width: r[2] * SCALE,
      depth: r[3] * SCALE,      // depth extends in -Z direction (away from viewer)
    }))
}

/**
 * Parse ceiling.csv — piecewise-linear ceiling height profile along X.
 * Each row: coordX, ceilingHeight
 * Segments are sorted ascending by X after parsing.
 */
export function parseCeilingCSV(csv: string): CeilingProfile {
  const rows = parseNumericRows(csv)
  const segments: CeilingSegment[] = rows
    .filter(r => r.length >= 2 && !r.some(isNaN))
    .map(r => ({ x: r[0] * SCALE, height: r[1] * SCALE }))
    .sort((a, b) => a.x - b.x)
  return { segments }
}

/**
 * Parse types_of_bays.csv — 7 columns (may have header row).
 * Columns: type_id, width_mm, depth_mm, height_mm, col4, count, col6
 * Returns typed BayTypeConfig[].
 */
export function parseBaysCSV(csv: string): BayTypeConfig[] {
  const rows = parseMixedRows(csv)
  const result: BayTypeConfig[] = []

  console.group('[WarehouseOS] types_of_bays.csv parsed')
  console.log('Columns: type_id | width_mm | depth_mm | height_mm | col4 | count | col6')

  for (const parts of rows) {
    if (parts.length < 7) continue
    const [typeId, widthStr, depthStr, heightStr, col4, countStr, col6] = parts
    const width  = parseFloat(widthStr)
    const depth  = parseFloat(depthStr)
    const height = parseFloat(heightStr)
    const count  = parseInt(countStr, 10)
    if (isNaN(width) || isNaN(depth) || isNaN(height) || isNaN(count)) continue

    const config: BayTypeConfig = {
      typeId,
      width:  width  * SCALE,
      depth:  depth  * SCALE,
      height: height * SCALE,
      col4,
      count,
      col6,
      // TODO: col4 appears to be a load/weight category label (e.g. "heavy", "medium", "light")
      // TODO: col6 appears to be a priority/tier number (e.g. 1, 2, 3)
    }
    result.push(config)
    console.log(`  ${typeId}: ${width}×${depth}×${height}mm, count=${count}, col4="${col4}", col6="${col6}"`)
  }

  console.groupEnd()
  return result
}

// ─── Utilities ────────────────────────────────────────────────────────────────

/**
 * Returns the ceiling height at a given Three.js X coordinate by linearly
 * interpolating between the two nearest breakpoints in the ceiling profile.
 * Clamps to the first/last segment height when X is out of profile range.
 */
export function getCeilingHeight(profile: CeilingProfile, x: number): number {
  const { segments } = profile
  if (segments.length === 0) return 30 // fallback: 3000 mm
  if (segments.length === 1) return segments[0].height
  if (x <= segments[0].x) return segments[0].height
  const last = segments[segments.length - 1]
  if (x >= last.x) return last.height

  for (let i = 0; i < segments.length - 1; i++) {
    const a = segments[i]
    const b = segments[i + 1]
    if (x >= a.x && x <= b.x) {
      const t = (x - a.x) / (b.x - a.x)
      return a.height + t * (b.height - a.height)
    }
  }

  return last.height
}

/**
 * Bounding box of the warehouse polygon (axis-aligned, Three.js units).
 */
export function computeWarehouseBounds(polygon: WarehousePolygon): WarehouseBounds {
  const xs = polygon.points.map(p => p.x)
  const zs = polygon.points.map(p => p.z)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minZ = Math.min(...zs)
  const maxZ = Math.max(...zs)
  return { minX, maxX, minZ, maxZ, width: maxX - minX, depth: maxZ - minZ }
}

/**
 * Centre of the warehouse bounding box — used as the camera orbit target.
 * Returns [centroidX, centroidZ] in Three.js coordinates.
 */
export function computeWarehouseCentroid(polygon: WarehousePolygon): [number, number] {
  const b = computeWarehouseBounds(polygon)
  return [(b.minX + b.maxX) / 2, (b.minZ + b.maxZ) / 2]
}

// ─── Polygon Clipping (Sutherland-Hodgman) ────────────────────────────────────

/**
 * Clips a polygon (in Three.js XZ space) to the vertical strip [xMin, xMax].
 * Uses Sutherland-Hodgman algorithm clipping against two vertical planes.
 * Returns the clipped polygon vertices (may be empty if no intersection).
 * All coordinates are already in Three.js units when this is called.
 */
export function clipPolygonToXStrip(polygon: Point2D[], xMin: number, xMax: number): Point2D[] {
  if (polygon.length < 3) return []

  // Clip against x >= xMin (keep points where x >= xMin)
  let clipped = clipAgainstPlane(polygon, (p) => p.x >= xMin, (a, b) => {
    // Intersection of edge AB with x = xMin
    const t = (xMin - a.x) / (b.x - a.x)
    return { x: xMin, z: a.z + t * (b.z - a.z) }
  })

  if (clipped.length < 3) return []

  // Clip against x <= xMax (keep points where x <= xMax)
  clipped = clipAgainstPlane(clipped, (p) => p.x <= xMax, (a, b) => {
    // Intersection of edge AB with x = xMax
    const t = (xMax - a.x) / (b.x - a.x)
    return { x: xMax, z: a.z + t * (b.z - a.z) }
  })

  return clipped
}

function clipAgainstPlane(
  polygon: Point2D[],
  inside: (p: Point2D) => boolean,
  intersect: (a: Point2D, b: Point2D) => Point2D,
): Point2D[] {
  if (polygon.length === 0) return []
  const output: Point2D[] = []
  const n = polygon.length

  for (let i = 0; i < n; i++) {
    const current = polygon[i]
    const next = polygon[(i + 1) % n]
    const currentInside = inside(current)
    const nextInside = inside(next)

    if (currentInside) {
      output.push(current)
      if (!nextInside) {
        output.push(intersect(current, next))
      }
    } else if (nextInside) {
      output.push(intersect(current, next))
    }
  }

  return output
}

// ─── Point-in-Polygon (Ray Casting) ──────────────────────────────────────────

/**
 * Ray-casting point-in-polygon test.
 * Casts a ray along +X from the point and counts edge crossings.
 * Odd number of crossings = inside.
 */
export function isInsidePolygon(point: Point2D, polygon: Point2D[]): boolean {
  const { x, z } = point
  const n = polygon.length
  let inside = false

  for (let i = 0, j = n - 1; i < n; j = i++) {
    const xi = polygon[i].x, zi = polygon[i].z
    const xj = polygon[j].x, zj = polygon[j].z

    const intersect =
      ((zi > z) !== (zj > z)) &&
      (x < (xj - xi) * (z - zi) / (zj - zi) + xi)

    if (intersect) inside = !inside
  }

  return inside
}

// ─── Bay Placement ────────────────────────────────────────────────────────────

const WALL_INSET = 1.0   // 100mm in Three.js units — keep bays away from walls
const AISLE_GAP  = 0.5   // gap between rows
const BAY_GAP    = 0.3   // gap between bays in the same row

/**
 * Place all bays from the parsed bay types into the warehouse polygon,
 * avoiding obstacles and walls, using a row-by-row grid scan.
 * Bay types are processed tallest-first.
 */
export function placeBays(
  bayTypes: BayTypeConfig[],
  polygon: WarehousePolygon,
  obstacles: ObstacleConfig[],
  ceilingProfile: CeilingProfile,
): PlacedBay[] {
  const bounds = computeWarehouseBounds(polygon)
  const startX = bounds.minX + WALL_INSET
  const startZ = bounds.minZ + WALL_INSET
  const endX   = bounds.maxX - WALL_INSET
  const endZ   = bounds.maxZ - WALL_INSET

  const placed: PlacedBay[] = []
  let bayCounter = 0

  // Sort bay types tallest first
  const sortedTypes = [...bayTypes].sort((a, b) => b.height - a.height)

  for (const bayType of sortedTypes) {
    let placedCount = 0
    let rowZ = startZ

    rowLoop: while (placedCount < bayType.count && rowZ + bayType.depth <= endZ + 0.01) {
      let colX = startX

      while (colX + bayType.width <= endX + 0.01) {
        if (placedCount >= bayType.count) break rowLoop

        // The bay footprint in XZ: [colX, rowZ] to [colX+w, rowZ+d]
        const footprintCorners: Point2D[] = [
          { x: colX,                z: rowZ },
          { x: colX + bayType.width, z: rowZ },
          { x: colX + bayType.width, z: rowZ + bayType.depth },
          { x: colX,                z: rowZ + bayType.depth },
        ]

        // Check all 4 corners are inside the polygon
        const allInside = footprintCorners.every(c => isInsidePolygon(c, polygon.points))

        if (allInside && !collides(colX, rowZ, bayType.width, bayType.depth, placed, obstacles)) {
          // Cap height at ceiling minus 0.3 clearance
          const centerX = colX + bayType.width / 2
          const maxH = getCeilingHeight(ceilingProfile, centerX) - 0.3
          const finalHeight = Math.min(bayType.height, Math.max(0.1, maxH))

          placed.push({
            id: `bay-${bayCounter++}`,
            typeId: bayType.typeId,
            position: [colX + bayType.width / 2, 0, rowZ + bayType.depth / 2],
            width: bayType.width,
            depth: bayType.depth,
            height: finalHeight,
            bayTypeData: bayType,
          })
          placedCount++
        }

        colX += bayType.width + BAY_GAP
      }

      rowZ += bayType.depth + AISLE_GAP
    }

    console.log(`[WarehouseOS] Bay type ${bayType.typeId}: placed ${placedCount}/${bayType.count}`)
  }

  return placed
}

function collides(
  x: number, z: number, w: number, d: number,
  placed: PlacedBay[],
  obstacles: ObstacleConfig[],
): boolean {
  // Check against already-placed bays
  for (const bay of placed) {
    const bx = bay.position[0] - bay.width / 2
    const bz = bay.position[2] - bay.depth / 2
    if (rectsOverlap(x, z, w, d, bx, bz, bay.width, bay.depth)) return true
  }

  // Check against obstacles
  for (const obs of obstacles) {
    // obs.z = -(csvY * SCALE) — already in Three.js coords, depth is positive size
    // So the obstacle spans from obs.z to obs.z + obs.depth in Z
    const obsMinZ = Math.min(obs.z, obs.z + obs.depth)
    const obsMaxZ = Math.max(obs.z, obs.z + obs.depth)
    const obsMinX = obs.x
    const obsMaxX = obs.x + obs.width
    if (rectsOverlap(x, z, w, d, obsMinX, obsMinZ, obsMaxX - obsMinX, obsMaxZ - obsMinZ)) return true
  }

  return false
}

function rectsOverlap(
  ax: number, az: number, aw: number, ad: number,
  bx: number, bz: number, bw: number, bd: number,
): boolean {
  return ax < bx + bw && ax + aw > bx &&
         az < bz + bd && az + ad > bz
}
