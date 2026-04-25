"use client"

import type { PlacedBay } from "@/lib/warehouse-service"

type Props = {
  bay: PlacedBay
  onClearSelection: () => void
}

// Hash a string to pick a colour from a set of badge colours
function hashTypeColor(typeId: string): { bg: string; text: string; border: string } {
  let hash = 0
  for (let i = 0; i < typeId.length; i++) {
    hash = typeId.charCodeAt(i) + ((hash << 5) - hash)
  }
  const colors: Array<{ bg: string; text: string; border: string }> = [
    { bg: "rgba(49,130,206,0.2)",  text: "#63b3ed", border: "rgba(49,130,206,0.4)"  }, // blue
    { bg: "rgba(56,161,105,0.2)",  text: "#68d391", border: "rgba(56,161,105,0.4)"  }, // green
    { bg: "rgba(214,158,46,0.2)",  text: "#f6e05e", border: "rgba(214,158,46,0.4)"  }, // amber
    { bg: "rgba(128,90,213,0.2)",  text: "#b794f4", border: "rgba(128,90,213,0.4)"  }, // purple
  ]
  return colors[Math.abs(hash) % colors.length]
}

function statRow(label: string, value: string) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em", color: "rgba(255,255,255,0.4)" }}>
        {label}
      </span>
      <span style={{ fontSize: 14, fontWeight: 600, color: "rgba(255,255,255,0.9)", fontFamily: "monospace" }}>
        {value}
      </span>
    </div>
  )
}

export function InfoPanel({ bay, onClearSelection }: Props) {
  const { bayTypeData } = bay
  const badgeColor = hashTypeColor(bay.typeId)

  // Convert back to mm for display (Three.js units × 100 = mm)
  const widthMm  = Math.round(bay.width  * 100)
  const depthMm  = Math.round(bay.depth  * 100)
  const heightMm = Math.round(bay.height * 100)
  const levels   = Math.max(1, Math.floor(heightMm / 800))

  // Position in metres (Three.js units × 0.1 = metres from mm/100)
  const posX = (bay.position[0] * 0.1).toFixed(1)
  const posZ = (bay.position[2] * 0.1).toFixed(1)

  return (
    <div
      style={{
        position: "absolute",
        bottom: 16,
        left: 16,
        width: "min(92%, 380px)",
        borderRadius: 12,
        border: "1px solid rgba(255,255,255,0.10)",
        background: "rgba(26, 32, 44, 0.92)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        padding: "16px 18px",
        zIndex: 20,
        boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
      }}
    >
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{
            fontSize: 10,
            textTransform: "uppercase",
            letterSpacing: "0.15em",
            color: "rgba(255,255,255,0.4)",
            fontWeight: 500,
          }}>
            Bay
          </span>
          {/* Type badge */}
          <span style={{
            fontSize: 11,
            fontWeight: 700,
            padding: "2px 8px",
            borderRadius: 999,
            border: `1px solid ${badgeColor.border}`,
            background: badgeColor.bg,
            color: badgeColor.text,
            letterSpacing: "0.05em",
          }}>
            {bay.typeId}
          </span>
        </div>
        <button
          onClick={onClearSelection}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "rgba(255,255,255,0.45)",
            fontSize: 18,
            lineHeight: 1,
            padding: "2px 6px",
            borderRadius: 4,
            transition: "color 0.15s",
          }}
          onMouseOver={e => (e.currentTarget.style.color = "rgba(255,255,255,0.9)")}
          onMouseOut={e => (e.currentTarget.style.color = "rgba(255,255,255,0.45)")}
          aria-label="Close info panel"
        >
          ✕
        </button>
      </div>

      {/* Stats grid — 2 columns */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: "12px 16px",
        marginBottom: 14,
      }}>
        {statRow("Width",    `${widthMm}mm`)}
        {statRow("Depth",    `${depthMm}mm`)}
        {statRow("Height",   `${heightMm}mm`)}
        {statRow("Levels",   `${levels}`)}
        {statRow("Position", `X: ${posX}m`)}
        {statRow("Depth pos",`Z: ${posZ}m`)}
      </div>

      {/* Divider */}
      <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", marginBottom: 12 }} />

      {/* Additional Bay Attributes */}
      <div style={{ display: "flex", gap: 16 }}>
        <span style={{ fontSize: 11, color: "rgba(255,255,255,0.35)" }}>
          Gap: <span style={{ color: "rgba(255,255,255,0.6)" }}>{bayTypeData.gap}</span>
        </span>
        <span style={{ fontSize: 11, color: "rgba(255,255,255,0.35)" }}>
          nLoads: <span style={{ color: "rgba(255,255,255,0.6)" }}>{bayTypeData.nLoads}</span>
        </span>
        <span style={{ fontSize: 11, color: "rgba(255,255,255,0.35)" }}>
          Price: <span style={{ color: "rgba(255,255,255,0.6)" }}>{bayTypeData.price}</span>
        </span>
      </div>
    </div>
  )
}
