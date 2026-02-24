import axios from "axios"

export type MetaResponse = {
  providers: string[]
  pi?: {
    enabled: boolean
    backend?: string
  }
}

export async function getMeta(): Promise<MetaResponse> {
  const res = await axios.get("/api/meta")
  return res.data as MetaResponse
}

