import client from "../api/client";

export interface ImportRowError {
  row: number;
  field: string;
  message: string;
}

export interface ImportResult {
  imported_count: number;
  errors: ImportRowError[];
}

export async function downloadExcel(
  url: string,
  params: Record<string, string | undefined> = {},
  filename: string,
  timeoutMs: number = 60000,
): Promise<void> {
  const resp = await client.get(url, {
    params,
    responseType: "blob",
    timeout: timeoutMs,
  });
  const blob = new Blob([resp.data]);
  const urlObj = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = urlObj;
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(urlObj);
}

export async function uploadExcel(
  url: string,
  file: File,
  params: Record<string, string> = {},
  timeoutMs: number = 60000,
): Promise<ImportResult> {
  const formData = new FormData();
  formData.append("file", file);
  try {
    const resp = await client.post(url, formData, {
      params,
      headers: { "Content-Type": "multipart/form-data" },
      timeout: timeoutMs,
    });
    return resp.data as ImportResult;
  } catch (err: any) {
    if (err.response?.status === 422) {
      return err.response.data as ImportResult;
    }
    throw err;
  }
}
