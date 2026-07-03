import { apiFetch } from "./api";
import { 
  SignupResponse, 
  LoginResponse, 
  DashboardStatsResponse,
  User
} from "../types/auth";

export async function signupUser(data: any): Promise<SignupResponse> {
  return apiFetch<SignupResponse>("/signup", {
    method: "POST",
    body: data,
  });
}

export async function loginUser(data: any): Promise<LoginResponse> {
  return apiFetch<LoginResponse>("/login", {
    method: "POST",
    body: data,
  });
}

export async function fetchDashboardStats(): Promise<DashboardStatsResponse> {
  return apiFetch<DashboardStatsResponse>("/dashboard/stats", {
    method: "GET",
  });
}

export async function fetchAdminUsers(desiredRole?: string, skills?: string): Promise<any[]> {
  const params = new URLSearchParams();
  if (desiredRole) params.append("desired_role", desiredRole);
  if (skills) params.append("skills", skills);
  const queryString = params.toString();
  const url = `/admin/users${queryString ? `?${queryString}` : ""}`;
  return apiFetch<any[]>(url, {
    method: "GET",
  });
}

export async function fetchUserDetails(userId: number): Promise<any> {
  return apiFetch<any>(`/admin/users/${userId}/details`, {
    method: "GET",
  });
}

export async function fetchAdminMonitoringSummary(): Promise<any> {
  return apiFetch<any>("/admin/monitoring/summary", {
    method: "GET",
  });
}

export async function deleteUser(userId: number): Promise<any> {
  return apiFetch<any>(`/admin/users/${userId}`, {
    method: "DELETE",
  });
}

export async function toggleAdminStatus(userId: number): Promise<User> {
  return apiFetch<User>(`/admin/users/${userId}/toggle-admin`, {
    method: "POST",
  });
}


export async function forgotPassword(email: string): Promise<{ message: string; user_found?: boolean; email_sent?: boolean; email_provider?: string; outbox_dir?: string | null; reset_url?: string | null }> {
  return apiFetch<{ message: string; user_found?: boolean; email_sent?: boolean; email_provider?: string; outbox_dir?: string | null; reset_url?: string | null }>("/auth/forgot-password", {
    method: "POST",
    body: { email },
  });
}

export async function resetPassword(token: string, new_password: string): Promise<{ message: string }> {
  return apiFetch<{ message: string }>("/auth/reset-password", {
    method: "POST",
    body: { token, new_password },
  });
}

export async function verifyEmail(token: string): Promise<{ message: string }> {
  return apiFetch<{ message: string }>("/auth/verify-email", {
    method: "POST",
    body: { token },
  });
}
