"use client"

import * as THREE from "three"
import { getCeilingHeight, type CeilingProfile, type ObstacleConfig } from "@/lib/warehouse-service"

type Props = {
  obstacles: ObstacleConfig[]
  ceilingProfile: CeilingProfile
}

export function ObstacleGroup({ obstacles, ceilingProfile }: Props) {
  if (obstacles.length === 0) return null

  return (
    <group>
      {obstacles.map((obs, i) => {
        // BUG 1 FIX: obs.x and obs.z are already in Three.js coords (z negated from CSV).
        // The obstacle footprint spans [obs.x, obs.x+width] in X.
        // For Z: obs.z = -(csvY * SCALE) is the near corner (closest to viewer in +Z dir).
        // depth is always a positive dimension, so it spans obs.z to obs.z + depth in Z.
        // Both z and z+depth may be negative, but centre is always obs.z + depth/2.
        const centerX = obs.x + obs.width / 2
        // depth extends in -Z direction (CSV depth → -Z in Three.js)
        const centerZ = obs.z - obs.depth / 2
        const obsHeight = getCeilingHeight(ceilingProfile, centerX)

        const boxGeo = new THREE.BoxGeometry(obs.width, obsHeight, obs.depth)
        const edgesGeo = new THREE.EdgesGeometry(boxGeo)

        return (
          <group
            key={i}
            position={[centerX, obsHeight / 2, centerZ]}
          >
            <mesh castShadow receiveShadow>
              <boxGeometry args={[obs.width, obsHeight, obs.depth]} />
              {/* Warm red-orange pillar/obstruction — high visibility */}
              <meshStandardMaterial
                color="#c0392b"
                roughness={0.65}
                metalness={0.05}
                flatShading={false}
              />
            </mesh>
            {/* BUG 3: Edge outlines for obstacle boxes */}
            <lineSegments geometry={edgesGeo}>
              <lineBasicMaterial color="#c53030" linewidth={1} />
            </lineSegments>
          </group>
        )
      })}
    </group>
  )
}
