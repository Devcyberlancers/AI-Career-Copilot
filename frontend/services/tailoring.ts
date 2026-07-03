import { apiFetch } from "./api";
import { getToken } from "../src/lib/auth";

export interface TailoredResume {
  id: number;
  user_id: number;
  job_id?: number | null;
  job_title?: string | null;
  company?: string | null;
  platform?: string | null;
  match_score?: number | null;
  job_description?: string | null;
  tailored_resume_text?: string | null;
  pdf_path?: string | null;
  pdf_url?: string | null;
  preview_url?: string | null;
  download_url?: string | null;
  original_resume_path?: string | null;
  tailored_resume_path?: string | null;
  original_match_score?: number | null;
  tailored_match_score?: number | null;
  improvement_score?: number | null;
  before_score?: number | null;
  after_score?: number | null;
  improvement?: number | null;
  matched_keywords: string[];
  missing_keywords: string[];
  sections_modified: string[];
  resume_used?: "original" | "tailored" | string | null;
  recommendation?: string | null;
  reason?: string | null;
  confidence?: number | null;
  missing_skills: string[];
  created_at: string;
  updated_at: string;
}

export interface TailorResumePayload {
  job_id?: number;
  job_title: string;
  company: string;
  job_description: string;
}

export interface TailorResumeResponse {
  success: boolean;
  message: string;
  resume_id: number;
  pdf_url: string;
  preview_url: string;
  download_url: string;
  tailored_resume_text: string;
  before_score?: number | null;
  after_score?: number | null;
  improvement?: number | null;
  resume_used?: "original" | "tailored" | string | null;
  reason?: string | null;
  confidence?: number | null;
  generated_at: string;
  tailored_resume: TailoredResume;
}

export async function tailorResume(payload: TailorResumePayload): Promise<TailorResumeResponse> {
  return apiFetch<TailorResumeResponse>("/api/resume/tailor", {
    method: "POST",
    body: payload,
  });
}

export async function fetchTailoredResumeHistory(): Promise<TailoredResume[]> {
  return apiFetch<TailoredResume[]>("/api/resume/tailored", {
    method: "GET",
  });
}

export async function fetchTailoredResumeForJob(jobId: number): Promise<TailoredResume> {
  return apiFetch<TailoredResume>(`/api/resume/tailored/job/${jobId}`, {
    method: "GET",
  });
}

function absoluteApiUrl(url: string): string {
  if (/^https?:\/\//i.test(url)) {
    return url;
  }
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
  return `${baseUrl}${url.startsWith("/") ? url : `/${url}`}`;
}

export function originalResumeDownloadUrl(tailoredResumeId: number): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
  return `${baseUrl}/api/resume/tailored/${tailoredResumeId}/download/original`;
}

export async function fetchResumeBlobByUrl(url: string, fallbackMessage: string): Promise<Blob> {
  const token = getToken();
  const response = await fetch(absoluteApiUrl(url), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    let message = fallbackMessage;
    try {
      const errorData = await response.json();
      message = errorData.detail || errorData.message || message;
    } catch {
      message = response.statusText || message;
    }
    throw new Error(message);
  }

  return response.blob();
}

export async function previewTailoredResume(resumeUrl: string): Promise<void> {
  const blob = await fetchResumeBlobByUrl(resumeUrl, "Could not preview resume.");
  const objectUrl = window.URL.createObjectURL(blob);
  window.open(objectUrl, "_blank", "noopener,noreferrer");
  setTimeout(() => window.URL.revokeObjectURL(objectUrl), 60_000);
}

export async function downloadResumeFromUrl(url: string, fileName = "tailored_resume.pdf"): Promise<void> {
  const blob = await fetchResumeBlobByUrl(url, "Could not download resume.");
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
}

export async function downloadTailoredResumeFile(
  tailoredResumeId: number,
  version: "original" | "tailored" = "original"
): Promise<void> {
  if (version === "tailored") {
    throw new Error("Tailored resume downloads must use the stored pdf_url from the backend response.");
  }
  const token = getToken();
  const blob = await fetch(originalResumeDownloadUrl(tailoredResumeId), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  }).then(async response => {
    if (!response.ok) throw new Error("Could not download resume.");
    return response.blob();
  });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${version}_resume_${tailoredResumeId}.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
