import { apiFetch } from "./api";
import { CandidateProfileData, UserProfileData } from "../types/profile";

export async function createProfile(profile: UserProfileData): Promise<UserProfileData> {
  return apiFetch<UserProfileData>("/api/profile/create", {
    method: "POST",
    body: profile,
  });
}

export async function fetchMyProfile(): Promise<UserProfileData> {
  return apiFetch<UserProfileData>("/api/profile/me", {
    method: "GET",
  });
}

export async function updateProfile(profile: UserProfileData): Promise<UserProfileData> {
  return apiFetch<UserProfileData>("/api/profile/update", {
    method: "PUT",
    body: profile,
  });
}

export async function fetchCandidateProfile(): Promise<CandidateProfileData> {
  return apiFetch<CandidateProfileData>("/api/candidate-profile/me", {
    method: "GET",
  });
}
