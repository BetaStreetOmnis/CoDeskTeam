import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"

function normalizeProxyHost(host: string | undefined): string {
  const h = (host ?? "").trim()
  if (!h) return "127.0.0.1"
  // 0.0.0.0 / :: are bind addresses, not good proxy targets.
  if (h === "0.0.0.0" || h === "::") return "127.0.0.1"
  return h
}

const apiHost = normalizeProxyHost(process.env.AISTAFF_API_HOST)
const apiPort = (process.env.AISTAFF_API_PORT ?? "8000").trim() || "8000"
const apiTarget = `http://${apiHost}:${apiPort}`

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      "/api": apiTarget,
      "/health": apiTarget,
    },
  },
})
