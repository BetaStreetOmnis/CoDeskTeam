import { createApp } from "vue"

function installCryptoRandomUUIDPolyfill(): void {
  // Some browsers (or non-secure contexts) don't implement crypto.randomUUID.
  // A few deps assume it exists, so we polyfill it early.
  const g = globalThis as any
  const c = g?.crypto
  if (!c) return
  if (typeof c.randomUUID === "function") return

  c.randomUUID = () => {
    if (typeof c.getRandomValues === "function") {
      const bytes = new Uint8Array(16)
      c.getRandomValues(bytes)
      // RFC 4122 v4
      bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40
      bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80
      const hex = Array.from(bytes, (b: number) => b.toString(16).padStart(2, "0"))
      return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex
        .slice(8, 10)
        .join("")}-${hex.slice(10, 16).join("")}`
    }

    // Last-resort fallback: not cryptographically strong, but OK for client-side ids.
    const s4 = () => Math.floor((1 + Math.random()) * 0x10000).toString(16).slice(1)
    return `${s4()}${s4()}-${s4()}-${s4()}-${s4()}-${s4()}${s4()}${s4()}`
  }
}

installCryptoRandomUUIDPolyfill()

async function bootstrap() {
  // Import App after polyfills are installed, so deps that call crypto.randomUUID during module init won't crash.
  const { default: App } = await import("./App.vue")
  createApp(App).mount("#app")
}

void bootstrap()
