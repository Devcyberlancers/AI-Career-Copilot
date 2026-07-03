import { apiFetch } from "./api";

export interface NotificationSettings {
  email_notifications: boolean;
  resume_ready: boolean;
  job_alerts: boolean;
  weekly_report: boolean;
  interview_reminder: boolean;
  security_alerts: boolean;
  marketing_emails: boolean;
  application_updates: boolean;
}

export interface ApplicationSettings {
  mode: "manual" | "automatic";
  auto_apply_enabled: boolean;
  minimum_match_score: number;
  preferred_companies: string[];
  preferred_locations: string[];
  salary_range: Record<string, unknown>;
  experience_range: Record<string, unknown>;
  remote_only: boolean;
  exclude_companies: string[];
  maximum_daily_applications: number;
  working_hours: Record<string, unknown>;
  daily_job_search_enabled: boolean;
  daily_job_search_time: string;
  daily_job_search_platforms: string[];
  jobs_per_platform: number;
}

export interface NotificationItem {
  id: number;
  type: string;
  title: string;
  message: string;
  action_url?: string | null;
  is_read: boolean;
  created_at: string;
}

export interface EmailLogItem {
  id: number;
  to_email: string;
  subject: string;
  template_name?: string | null;
  provider: string;
  status: string;
  attempts: number;
  error_message?: string | null;
  sent_at?: string | null;
  created_at: string;
}

export interface UsageLimitItem {
  platform: string;
  used: number;
  limit: number;
  remaining: number;
  reset_at: string;
}

export function fetchNotificationSettings() {
  return apiFetch<NotificationSettings>("/api/settings/notifications");
}

export function updateNotificationSettings(payload: NotificationSettings) {
  return apiFetch<NotificationSettings>("/api/settings/notifications", {
    method: "POST",
    body: payload,
  });
}

export function fetchApplicationSettings() {
  return apiFetch<ApplicationSettings>("/api/settings/application-mode");
}

export function updateApplicationSettings(payload: ApplicationSettings) {
  return apiFetch<ApplicationSettings>("/api/settings/application-mode", {
    method: "POST",
    body: payload,
  });
}

export function fetchNotifications() {
  return apiFetch<NotificationItem[]>("/api/notifications");
}

export function fetchEmailHistory() {
  return apiFetch<EmailLogItem[]>("/api/email/history");
}

export function sendTestEmail(template_name = "welcome") {
  return apiFetch<{ success: boolean; sent: boolean; to_email: string }>("/api/email/test", {
    method: "POST",
    body: { template_name },
  });
}

export function fetchUsageLimits() {
  return apiFetch<UsageLimitItem[]>("/api/limits");
}
