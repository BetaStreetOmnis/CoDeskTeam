import axios from "axios"

export async function browserStart(sessionId: string): Promise<void> {
  await axios.post("/api/browser/start", { session_id: sessionId })
}

export async function browserNavigate(sessionId: string, url: string): Promise<void> {
  await axios.post("/api/browser/navigate", { session_id: sessionId, url })
}

export async function browserScreenshot(sessionId: string): Promise<{ image_base64: string }> {
  const res = await axios.post("/api/browser/screenshot", { session_id: sessionId })
  return res.data
}

