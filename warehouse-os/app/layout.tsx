import type { Metadata } from "next"
import { Montserrat, Space_Mono } from "next/font/google"
import "./globals.css"
import { ThemeProvider } from "@/components/theme-provider"
import { cn } from "@/lib/utils"

const montserrat = Montserrat({
  subsets: ["latin"],
  variable: "--font-sans",
})

const spaceMono = Space_Mono({
  subsets: ["latin"],
  variable: "--font-heading",
  weight: ["400", "700"],
})

export const metadata: Metadata = {
  title: "WarehouseOS",
  description: "3D Interactive Warehouse Visualiser",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={cn(
        "dark antialiased",
        montserrat.variable,
        spaceMono.variable,
        "font-sans",
      )}
    >
      <body>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  )
}
