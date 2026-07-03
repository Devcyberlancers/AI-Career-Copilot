import { apiFetch } from "./api";
import { ResumeDetails } from "../types/profile";

export async function uploadResume(file: File): Promise<ResumeDetails> {
  const formData = new FormData();
  formData.append("file", file);
  
  return apiFetch<ResumeDetails>("/api/resume/upload", {
    method: "POST",
    body: formData,
  });
}

export async function fetchMyResume(): Promise<ResumeDetails> {
  return apiFetch<ResumeDetails>("/api/resume/me", {
    method: "GET",
  });
}

export async function deleteMyResume(): Promise<{ message: string }> {
  return apiFetch<{ message: string }>("/api/resume/delete", {
    method: "DELETE",
  });
}
