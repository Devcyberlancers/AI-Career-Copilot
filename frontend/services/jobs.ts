import { apiFetch } from "./api";

export const SUPPORTED_JOB_SOURCE = "Naukri" as const;
export const JOB_SOURCES = ["Naukri", "LinkedIn", "Foundit", "Indeed", "Wellfound", "Cutshort", "Hirist"] as const;
export type StoredJobSource = typeof JOB_SOURCES[number];
export type JobDiscoverySource = StoredJobSource | "All";

export type JobStatus = "Discovered" | "Saved" | "Applied" | "Skipped";

export interface MatchScoreBreakdown {
  semantic?: number;
  model?: string;
  recommendations?: string[];
  requirement_matches?: Array<{
    requirement: string;
    candidate_term: string;
    similarity: number;
  }>;
  explanations?: Record<string, string>;
  scoring_engine?: string;
}

export interface Job {
  id: number;
  user_id: number;
  title: string;
  company: string;
  location?: string;
  description?: string;
  apply_url?: string;
  source?: StoredJobSource;
  status: JobStatus;
  match_score?: number;
  semantic_score?: number;
  confidence?: number;
  matched_skills: string[];
  missing_skills: string[];
  matched_tools: string[];
  missing_tools: string[];
  experience_gap: number;
  score_breakdown_json: MatchScoreBreakdown;
  created_at: string;
  updated_at: string;
}

export interface JobMatchAnalysis {
  job_id: number;
  match_score?: number;
  semantic_score?: number;
  matched_skills: string[];
  missing_skills: string[];
  recommendations: string[];
  explanation: string;
  model: string;
}

export function isValidSupportedJobUrl(url?: string, source?: string): url is string {
  if (!url) return false;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:") return false;
    if (source === "LinkedIn") {
      return parsed.hostname === "linkedin.com" || parsed.hostname.endsWith(".linkedin.com");
    }
    if (source === "Foundit") {
      return parsed.hostname.endsWith("foundit.in") || parsed.hostname.endsWith("foundit.com");
    }
    if (source === "Wellfound") {
      return parsed.hostname === "wellfound.com" || parsed.hostname.endsWith(".wellfound.com");
    }
    if (source === "Hirist") {
      return parsed.hostname.endsWith("hirist.tech") || parsed.hostname.endsWith("hirist.com");
    }
    if (source === "Cutshort") {
      return parsed.hostname === "cutshort.io" || parsed.hostname.endsWith(".cutshort.io");
    }
    if (source === "Indeed") {
      return parsed.hostname.endsWith("indeed.com") || parsed.hostname.endsWith("indeed.co.in");
    }
    return parsed.hostname === "naukri.com" || parsed.hostname.endsWith(".naukri.com");
  } catch {
    return false;
  }
}

export function isValidNaukriJobUrl(url?: string): url is string {
  return isValidSupportedJobUrl(url, "Naukri");
}

export interface JobAdminItem extends Job {
  user_name: string;
  user_email: string;
}

export async function fetchUserJobs(): Promise<Job[]> {
  return apiFetch<Job[]>("/api/jobs/me", {
    method: "GET",
  });
}

export interface DiscoverJobsResponse {
  success: boolean;
  error?: "DAILY_LIMIT_REACHED" | string;
  query?: string;
  location?: string;
  source?: JobDiscoverySource;
  max_results?: number;
  jobs_found?: number;
  jobs_stored?: number;
  jobs_skipped?: number;
  stored_jobs_count?: number;
  duplicates_removed?: number;
  jobs_discovered_in_last_24_hours?: number;
  remaining_jobs?: number;
  daily_limit?: number;
  next_available_at?: string | null;
  remaining_seconds?: number;
  jobs?: Array<{
    title: string;
    company: string;
    location: string;
    description: string;
    apply_url: string;
    source: StoredJobSource;
  }>;
}

export interface PlatformStat {
  source: StoredJobSource;
  count: number;
  last_refresh_at?: string | null;
}

export interface PlatformStatsResponse {
  total: number;
  sources: PlatformStat[];
}

export async function discoverJobs(source: JobDiscoverySource = "Naukri"): Promise<DiscoverJobsResponse> {
  return apiFetch<DiscoverJobsResponse>("/api/jobs/discover", {
    method: "POST",
    body: { source },
  });
}

export async function discoverJobsFromNaukri(): Promise<DiscoverJobsResponse> {
  return discoverJobs("Naukri");
}

export async function refreshAllJobPlatforms(): Promise<DiscoverJobsResponse> {
  return apiFetch<DiscoverJobsResponse>("/api/jobs/refresh-all", {
    method: "POST",
  });
}

export async function refreshJobPlatform(source: StoredJobSource): Promise<DiscoverJobsResponse> {
  return apiFetch<DiscoverJobsResponse>(`/api/jobs/refresh/${source}`, {
    method: "POST",
  });
}

export async function fetchPlatformStats(): Promise<PlatformStatsResponse> {
  return apiFetch<PlatformStatsResponse>("/api/jobs/stats/platforms", {
    method: "GET",
  });
}

export async function fetchJobsBySource(source: StoredJobSource): Promise<Job[]> {
  return apiFetch<Job[]>(`/api/jobs/source/${source}`, {
    method: "GET",
  });
}

export async function fetchJobDetails(jobId: number): Promise<Job> {
  return apiFetch<Job>(`/api/jobs/${jobId}`, {
    method: "GET",
  });
}

export async function fetchJobMatchAnalysis(jobId: number): Promise<JobMatchAnalysis> {
  return apiFetch<JobMatchAnalysis>(`/api/jobs/${jobId}/match-analysis`, {
    method: "GET",
  });
}

export async function updateJobStatus(jobId: number, status: JobStatus): Promise<{ success: boolean }> {
  return apiFetch<{ success: boolean }>(`/api/jobs/${jobId}/status`, {
    method: "PUT",
    body: { status },
  });
}

export async function fetchAdminJobs(filters: {
  source?: string;
  status?: string;
  company?: string;
  title?: string;
} = {}): Promise<JobAdminItem[]> {
  const params = new URLSearchParams();
  if (filters.source) params.append("source", filters.source);
  if (filters.status) params.append("status", filters.status);
  if (filters.company) params.append("company", filters.company);
  if (filters.title) params.append("title", filters.title);
  
  const queryString = params.toString();
  const url = `/admin/jobs${queryString ? `?${queryString}` : ""}`;
  
  return apiFetch<JobAdminItem[]>(url, {
    method: "GET",
  });
}
