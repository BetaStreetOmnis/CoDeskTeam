import axios from "axios"

export type UploadImageResponse = { file_id: string; filename: string; content_type: string; download_url: string }

export type UploadFileResponse = {
  file_id: string
  filename: string
  content_type: string
  size_bytes: number
  download_url: string
}

export type FilePreviewResponse = {
  kind: string
  file_id: string
  download_url: string
  preview_url?: string | null
  preview_images?: string[] | null
}

export async function uploadImage(file: File, opts?: { project_id?: number }): Promise<UploadImageResponse> {
  const fd = new FormData()
  fd.append("file", file)
  const project_id = opts?.project_id && opts.project_id > 0 ? opts.project_id : undefined
  const res = await axios.post("/api/files/upload-image", fd, { params: project_id ? { project_id } : undefined })
  return res.data as UploadImageResponse
}

export async function uploadFile(file: File, opts?: { project_id?: number }): Promise<UploadFileResponse> {
  const fd = new FormData()
  fd.append("file", file)
  const project_id = opts?.project_id && opts.project_id > 0 ? opts.project_id : undefined
  const res = await axios.post("/api/files/upload-file", fd, { params: project_id ? { project_id } : undefined })
  return res.data as UploadFileResponse
}

export async function getFilePreview(fileId: string): Promise<FilePreviewResponse> {
  const res = await axios.get(`/api/files/preview/${encodeURIComponent(fileId)}`)
  return res.data as FilePreviewResponse
}
