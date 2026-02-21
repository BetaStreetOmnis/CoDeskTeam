import axios from "axios"

export type BuiltinSkill = {
  id: string
  name: string
  description: string
  endpoint: string
  default_payload: unknown
}

export async function listSkills(): Promise<BuiltinSkill[]> {
  const res = await axios.get("/api/skills")
  return res.data as BuiltinSkill[]
}

export async function runSkill(endpoint: string, payload: unknown, params?: Record<string, any>): Promise<any> {
  const res = await axios.post(endpoint, payload, params ? { params } : undefined)
  return res.data
}
