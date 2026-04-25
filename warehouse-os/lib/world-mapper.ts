import type { WorldResponse } from "./api"
import type {
  BayTypeConfig,
  CeilingProfile,
  ObstacleConfig,
  PlacedBay,
  WarehousePolygon,
} from "./warehouse-service"

const SCALE = 1 / 100

export function mapWorldToScene(world: WorldResponse): {
  polygon: WarehousePolygon
  obstacles: ObstacleConfig[]
  ceilingProfile: CeilingProfile
  placedBays: PlacedBay[]
  bayTypes: BayTypeConfig[]
} {
  const polygon: WarehousePolygon = {
    points: world.warehouse.perimeter.map(p => ({
      x: p.x * SCALE,
      z: -(p.y * SCALE),
    })),
  }

  const obstacles: ObstacleConfig[] = world.obstacles.map(o => ({
    x: o.x * SCALE,
    z: -(o.y * SCALE),
    width: o.width * SCALE,
    depth: o.depth * SCALE,
  }))

  const ceilingProfile: CeilingProfile = {
    segments: world.ceiling.map(s => ({
      x: s.xFrom * SCALE,
      height: s.maxHeight * SCALE,
    })),
  }

  const placedBays: PlacedBay[] = world.rows.flatMap(row =>
    row.bays.map(bay => {
      const { width, depth, height } = bay.dimensions

      // Backend now sends the exact physical center of the bay
      const centerX = bay.position.x * SCALE
      const centerZ = -(bay.position.y * SCALE)

      const bayTypeData: BayTypeConfig = {
        typeId: String(bay.typeId),
        width: width * SCALE,
        depth: depth * SCALE,
        height: height * SCALE,
        gap: 0,
        nLoads: bay.nLoads,
        price: bay.price,
      }

      return {
        id: bay.bayId,
        typeId: String(bay.typeId),
        position: [centerX, 0, centerZ] as [number, number, number],
        rotation: bay.rotation, // Exact geometric rotation passed through
        width: width * SCALE,
        depth: depth * SCALE,
        height: height * SCALE,
        bayTypeData,
      }
    })
  )

  // Synthetic entry so the "X / Y bays placed" chip shows the correct total
  const bayTypes: BayTypeConfig[] = [
    { typeId: "all", width: 0, depth: 0, height: 0, gap: 0, nLoads: 0, price: 0 },
  ]

  return { polygon, obstacles, ceilingProfile, placedBays, bayTypes }
}
