import axios from "axios"

export function setAuthToken(token: string | null) {
  if (!token) {
    delete axios.defaults.headers.common.Authorization
    return
  }
  axios.defaults.headers.common.Authorization = `Bearer ${token}`
}

export async function health() {
  return axios.get("/health")
}

