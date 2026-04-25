"use client"

import type { PlacedBay } from "@/lib/warehouse-service"
import { Bay } from "./bay"

type Props = {
  placedBays: PlacedBay[]
  selectedBayId: string | null
  onSelectBay: (bayId: string) => void
  viewMode?: "3d" | "floor_plan"
}

export function BayGroup({ placedBays, selectedBayId, onSelectBay, viewMode = "3d" }: Props) {
  if (placedBays.length === 0) return null

  return (
    <group>
      {placedBays.map(bay => (
        <Bay
          key={bay.id}
          bay={bay}
          isSelected={selectedBayId === bay.id}
          onSelectBay={onSelectBay}
          viewMode={viewMode}
        />
      ))}
    </group>
  )
}
