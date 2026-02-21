import axios from "axios"

export type AuthStatusResponse = { setup_required: boolean }

export type PublicTeam = { id: number; name: string }

export type SetupRequest = { team_name: string; name: string; email: string; password: string }
export type LoginRequest = { email: string; password: string; team_id?: number }

export type AuthResponse = {
  access_token: string
  token_type: "bearer"
  user: { id: number; email: string; name: string }
  teams: Array<{ id: number; name: string; role: string }>
  active_team: { id: number; name: string; role: string }
}

export type MeResponse = {
  user: { id: number; email: string; name: string }
  teams: Array<{ id: number; name: string; role: string }>
  active_team: { id: number; name: string; role: string }
}

export async function authStatus(): Promise<AuthStatusResponse> {
  const res = await axios.get("/api/auth/status")
  return res.data as AuthStatusResponse
}

export async function listAuthTeams(): Promise<PublicTeam[]> {
  const res = await axios.get("/api/auth/teams")
  return res.data as PublicTeam[]
}

export async function authSetup(req: SetupRequest): Promise<AuthResponse> {
  const res = await axios.post("/api/auth/setup", req)
  return res.data as AuthResponse
}

export async function authLogin(req: LoginRequest): Promise<AuthResponse> {
  const res = await axios.post("/api/auth/login", req)
  return res.data as AuthResponse
}

export async function authRegister(req: {
  invite_token: string
  team_id?: number
  name: string
  email: string
  password: string
}): Promise<AuthResponse> {
  const res = await axios.post("/api/auth/register", req)
  return res.data as AuthResponse
}

export async function getMe(): Promise<MeResponse> {
  const res = await axios.get("/api/me")
  return res.data as MeResponse
}

export async function switchTeam(team_id: number): Promise<AuthResponse> {
  const res = await axios.post("/api/auth/switch-team", { team_id })
  return res.data as AuthResponse
}
