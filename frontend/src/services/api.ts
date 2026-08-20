import type { ReviewRequest, ReviewResult, BatchResult, HealthResponse } from "@/types";

const BASE = import.meta.env.VITE_API_URL ?? "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`API ${res.status}: ${text}`);
  }

  return res.json();
}

/** POST /review — review a single buy lead */
export async function reviewSingle(payload: ReviewRequest): Promise<ReviewResult> {
  return request<ReviewResult>("/review", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** POST /batch — review multiple buy leads */
export async function reviewBatch(leads: ReviewRequest[]): Promise<BatchResult> {
  return request<BatchResult>("/batch", {
    method: "POST",
    body: JSON.stringify({ leads }),
  });
}

/** GET /health — health check */
export async function healthCheck(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}
