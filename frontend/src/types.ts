/** A single buy lead to be reviewed */
export interface ReviewRequest {
  offer_id?: string;
  title?: string;
  mcat?: string;
  isq_filled?: Record<string, string> | string;
  isq_asked?: Record<string, string> | string[];

  /* CSV-style aliases */
  eto_ofr_display_id?: string;
  eto_ofr_title?: string;
  glcat_mcat_name?: string;
  attributes_combined?: string;
}

/** The result returned from the API for a single review */
export interface ReviewResult {
  offer_id?: string;
  flags: string[];
  concise_reason: string;
}

/** Batch review response */
export interface BatchResult {
  results: ReviewResult[];
}

/** Health check response */
export interface HealthResponse {
  status: string;
  model: string;
  base_url: string;
}

/** Status of a review in the UI */
export type ReviewStatus = "idle" | "loading" | "success" | "error";
