"use client"

import { useMemo } from "react"

import { Color, PlaneGeometry, RingGeometry, UniformsLib, UniformsUtils } from "three"

type EarthBackdropProps = {
  centerX: number
  centerZ: number
  floorWidth: number
  floorDepth: number
}

function hashNoise(seed: number): number {
  const x = Math.sin(seed * 12.9898) * 43758.5453
  return x - Math.floor(x)
}

export function EarthBackdrop({
  centerX,
  centerZ,
  floorWidth,
  floorDepth,
}: EarthBackdropProps) {
  const terrainSize = Math.max(floorWidth, floorDepth) * 7
  const keepFlatRadius = Math.max(floorWidth, floorDepth) * 0.9

  const groundTerrainSize = terrainSize * 2.1
  const groundTerrainGeometry = useMemo(() => {
    return new PlaneGeometry(groundTerrainSize, groundTerrainSize, 160, 160)
  }, [groundTerrainSize])

  const groundShaderUniforms = useMemo(
    () =>
      UniformsUtils.merge([
        UniformsLib.fog,
        {
          uFlatRadius: { value: keepFlatRadius * 1.04 },
          uTerrainRadius: { value: groundTerrainSize * 0.52 },
          uGroundHeight: { value: Math.max(0.56, keepFlatRadius * 0.062) },
          uColorDark: { value: new Color("#b5d36e") },     // Pastel lime
          uColorMid: { value: new Color("#c4e07a") },      // Light pastel lime
          uColorDust: { value: new Color("#d2ec88") },     // Very light lime highlight
          uColorFogBlend: { value: new Color("#f4f8fa") }, // Matches the sky horizon
        },
      ]),
    [groundTerrainSize, keepFlatRadius]
  )

  const mountainRingGeometry = useMemo(() => {
    const innerRadius = keepFlatRadius * 1.95
    const outerRadius = terrainSize * 0.95
    return new RingGeometry(innerRadius, outerRadius, 220, 20)
  }, [keepFlatRadius, terrainSize])

  const mountainShaderUniforms = useMemo(
    () =>
      UniformsUtils.merge([
        UniformsLib.fog,
        {
          uInnerRadius: { value: keepFlatRadius * 1.95 },
          uOuterRadius: { value: terrainSize * 0.95 },
          uMountainHeight: { value: Math.max(2.5, terrainSize * 0.08) },
          uColorShadow: { value: new Color("#a9c864") },   // Pastel hill shadow
          uColorMid: { value: new Color("#b5d36e") },      // Pastel hill mid
          uColorTop: { value: new Color("#c4e07a") },      // Pastel peak
          uColorFogBlend: { value: new Color("#f4f8fa") }, // Matches the sky horizon
        },
      ]),
    [keepFlatRadius, terrainSize]
  )

  const rockMarkers = useMemo(() => {
    const result: Array<{ x: number; z: number; scale: number; rotation: number }> = []
    const inner = keepFlatRadius * 1.08
    const outer = keepFlatRadius * 1.82
    const count = 48
    for (let i = 0; i < count; i += 1) {
      const angle = (i / count) * Math.PI * 2 + (hashNoise(i + 7) - 0.5) * 0.2
      const radius = inner + hashNoise(i + 73) * (outer - inner)
      result.push({
        x: Math.cos(angle) * radius,
        z: Math.sin(angle) * radius,
        scale: 0.14 + hashNoise(i + 211) * 0.42,
        rotation: hashNoise(i + 319) * Math.PI,
      })
    }
    return result
  }, [keepFlatRadius])

  return (
    <group position={[centerX, 0, centerZ]}>
      <mesh
        geometry={groundTerrainGeometry}
        position={[0, -0.2, 0]}
        rotation={[-Math.PI / 2, 0, 0]}
        receiveShadow
      >
        <shaderMaterial
          uniforms={groundShaderUniforms}
          vertexShader={`
            varying float vElevation;
            varying float vRadius;
            varying vec2 vUv;

            uniform float uFlatRadius;
            uniform float uTerrainRadius;
            uniform float uGroundHeight;

            #include <fog_pars_vertex>

            float hash(vec2 p) {
              return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
            }

            float noise(vec2 p) {
              vec2 i = floor(p);
              vec2 f = fract(p);
              float a = hash(i);
              float b = hash(i + vec2(1.0, 0.0));
              float c = hash(i + vec2(0.0, 1.0));
              float d = hash(i + vec2(1.0, 1.0));
              vec2 u = f * f * (3.0 - 2.0 * f);
              return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
            }

            float fbm(vec2 p) {
              float value = 0.0;
              float amplitude = 0.5;
              for (int i = 0; i < 5; i++) {
                value += amplitude * noise(p);
                p *= 2.02;
                amplitude *= 0.53;
              }
              return value;
            }

            void main() {
              vec3 p = position;
              vUv = uv;
              float radius = length(p.xy);
              vRadius = radius;

              float centerLift = smoothstep(uFlatRadius * 0.9, uFlatRadius * 1.24, radius);
              float outerFade = 1.0 - smoothstep(uTerrainRadius * 0.8, uTerrainRadius, radius);
              float terrainMask = centerLift * outerFade;

              float lowBands = fbm(p.xy * 0.023) * 0.62;
              float mediumBands = fbm((p.xy + vec2(19.0, -43.0)) * 0.06) * 0.31;
              float micro = noise(p.xy * 0.17) * 0.08;
              float dunes = smoothstep(0.32, 1.0, lowBands + mediumBands + micro);
              float elevation = (dunes - 0.42) * uGroundHeight * terrainMask;
              p.z += elevation;
              vElevation = elevation;

              vec4 mvPosition = modelViewMatrix * vec4(p, 1.0);
              gl_Position = projectionMatrix * mvPosition;
              #include <fog_vertex>
            }
          `}
          fragmentShader={`
            varying float vElevation;
            varying float vRadius;
            varying vec2 vUv;

            uniform float uFlatRadius;
            uniform float uTerrainRadius;
            uniform float uGroundHeight;
            uniform vec3 uColorDark;
            uniform vec3 uColorMid;
            uniform vec3 uColorDust;
            uniform vec3 uColorFogBlend;

            #include <fog_pars_fragment>

            void main() {
              float radial01 = clamp(vRadius / max(0.0001, uTerrainRadius), 0.0, 1.0);
              float height01 = clamp((vElevation / max(0.0001, uGroundHeight)) * 0.5 + 0.5, 0.0, 1.0);
              float plateauBlend = smoothstep(uFlatRadius * 0.72, uFlatRadius * 1.24, vRadius);
              float edgeFade = 1.0 - smoothstep(0.9, 1.0, radial01);
              float dustMask = smoothstep(0.28, 0.9, height01) * (0.7 + vUv.y * 0.3);

              vec3 base = mix(uColorDark, uColorMid, smoothstep(0.2, 0.78, height01));
              vec3 plateau = mix(uColorDark, uColorMid, 0.35);
              vec3 terrainColor = mix(plateau, base, plateauBlend);
              vec3 withDust = mix(terrainColor, uColorDust, dustMask * 0.45 * plateauBlend);
              vec3 color = mix(withDust, uColorFogBlend, smoothstep(0.7, 1.0, radial01) * 0.42);
              vec3 edgeBlended = mix(uColorFogBlend, color, edgeFade);

              gl_FragColor = vec4(edgeBlended, 1.0);
              #include <fog_fragment>
            }
          `}
          fog
        />
      </mesh>

      {rockMarkers.map((marker, index) => (
        <mesh
          key={`earth-rock-${index}`}
          position={[marker.x, -0.07 + marker.scale * 0.2, marker.z]}
          rotation={[0, marker.rotation, 0]}
          scale={[marker.scale, marker.scale * 0.76, marker.scale * 1.18]}
          castShadow
          receiveShadow
        >
          <dodecahedronGeometry args={[0.45, 0]} />
          <meshStandardMaterial
            color="#8c918c"
            roughness={0.95}
            metalness={0.05}
          />
        </mesh>
      ))}

      <mesh
        geometry={mountainRingGeometry}
        position={[0, -0.32, 0]}
        rotation={[-Math.PI / 2, 0, 0]}
        receiveShadow
      >
        <shaderMaterial
          uniforms={mountainShaderUniforms}
          vertexShader={`
            varying float vElevation;
            varying float vRadius;

            uniform float uInnerRadius;
            uniform float uOuterRadius;
            uniform float uMountainHeight;

            #include <fog_pars_vertex>

            float hash(vec2 p) {
              return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
            }

            float noise(vec2 p) {
              vec2 i = floor(p);
              vec2 f = fract(p);

              float a = hash(i);
              float b = hash(i + vec2(1.0, 0.0));
              float c = hash(i + vec2(0.0, 1.0));
              float d = hash(i + vec2(1.0, 1.0));

              vec2 u = f * f * (3.0 - 2.0 * f);
              return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
            }

            float fbm(vec2 p) {
              float value = 0.0;
              float amplitude = 0.5;
              for (int i = 0; i < 5; i++) {
                value += amplitude * noise(p);
                p *= 2.03;
                amplitude *= 0.52;
              }
              return value;
            }

            void main() {
              vec3 p = position;
              float radius = length(p.xy);
              vRadius = radius;

              float ringSpan = max(1.0, uOuterRadius - uInnerRadius);
              float innerBand = smoothstep(uInnerRadius, uInnerRadius + ringSpan * 0.18, radius);
              float outerBand = 1.0 - smoothstep(uOuterRadius - ringSpan * 0.22, uOuterRadius, radius);
              float distanceMask = innerBand * outerBand;

              float ridge =
                fbm(p.xy * 0.012) * 0.72 +
                fbm((p.xy + vec2(53.0, -21.0)) * 0.028) * 0.33;
              float peak = 1.0 - abs(noise(p.xy * 0.017) * 2.0 - 1.0);
              float mountain = pow(max(0.0, ridge * 0.8 + peak * 0.55), 1.85);

              float elevation = mountain * uMountainHeight * distanceMask;
              p.z += elevation;
              vElevation = elevation;

              vec4 mvPosition = modelViewMatrix * vec4(p, 1.0);
              gl_Position = projectionMatrix * mvPosition;
              #include <fog_vertex>
            }
          `}
          fragmentShader={`
            varying float vElevation;
            varying float vRadius;

            uniform float uInnerRadius;
            uniform float uOuterRadius;
            uniform float uMountainHeight;
            uniform vec3 uColorShadow;
            uniform vec3 uColorMid;
            uniform vec3 uColorTop;
            uniform vec3 uColorFogBlend;

            #include <fog_pars_fragment>

            void main() {
              float radius01 = clamp((vRadius - uInnerRadius) / max(1.0, (uOuterRadius - uInnerRadius)), 0.0, 1.0);
              float elevation01 = clamp(vElevation / max(0.0001, uMountainHeight), 0.0, 1.0);
              float alpha = 1.0 - smoothstep(0.8, 1.0, radius01);

              vec3 base = mix(uColorShadow, uColorMid, smoothstep(0.05, 0.55, elevation01));
              vec3 peak = mix(base, uColorTop, smoothstep(0.45, 1.0, elevation01));
              vec3 color = mix(peak, uColorFogBlend, smoothstep(0.55, 1.0, radius01) * 0.45);

              if (alpha < 0.02) discard;
              gl_FragColor = vec4(color, 1.0);
              #include <fog_fragment>
            }
          `}
          fog
        />
      </mesh>
    </group>
  )
}
