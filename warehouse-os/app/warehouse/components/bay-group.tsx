"use client"

import type { PlacedBay } from "@/lib/warehouse-service"
import { Bay } from "./bay"

type Props = {
  placedBays: PlacedBay[]
  selectedBayId: string | null
  onSelectBay: (bayId: string) => void
}

export function BayGroup({ placedBays, selectedBayId, onSelectBay }: Props) {
  if (placedBays.length === 0) return null

  return (
    <group>
      {placedBays.map(bay => (
        <Bay
          key={bay.id}
          bay={bay}
          isSelected={selectedBayId === bay.id}
          onSelectBay={onSelectBay}
        />
      ))}
    </group>
  )
}
