import axios from "axios"

export type PrototypeRequest = {
  project_name: string
  pages: Array<{ title: string; description?: string; slug?: string }>
}

export async function generatePrototype(
  req: PrototypeRequest,
): Promise<{ file_id: string; filename: string; download_url: string; preview_url?: string; workspace_path?: string; workspace_context_path?: string }> {
  const res = await axios.post("/api/prototype/generate", req)
  return res.data
}
