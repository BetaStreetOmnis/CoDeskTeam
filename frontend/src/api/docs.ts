import axios from "axios"

export type PptRequest = {
  title: string
  slides: Array<{ title: string; bullets: string[] }>
  style?: "auto" | "modern_blue" | "minimal_gray" | "dark_tech" | "warm_business" | "template_jetlinks" | "template_team"
  layout_mode?: "auto" | "focus" | "single_column" | "two_column" | "cards"
}

export type QuoteRequest = {
  seller: string
  buyer: string
  currency: string
  items: Array<{ name: string; quantity: number; unit_price: number; unit?: string }>
  note?: string
}

export type PptCreateResponse = {
  file_id: string
  filename: string
  download_url: string
  style?: string
  layout_mode?: string
  preview_image_file_id?: string
  preview_image_url?: string
  workspace_path?: string
  workspace_context_path?: string
}

export async function createPpt(req: PptRequest): Promise<PptCreateResponse> {
  const res = await axios.post("/api/docs/ppt", req)
  return res.data as PptCreateResponse
}

export async function createQuote(
  req: QuoteRequest,
): Promise<{ file_id: string; filename: string; download_url: string; workspace_path?: string; workspace_context_path?: string }> {
  const res = await axios.post("/api/docs/quote", req)
  return res.data
}

export async function createQuoteXlsx(
  req: QuoteRequest,
): Promise<{ file_id: string; filename: string; download_url: string; workspace_path?: string; workspace_context_path?: string }> {
  const res = await axios.post("/api/docs/quote-xlsx", req)
  return res.data
}
