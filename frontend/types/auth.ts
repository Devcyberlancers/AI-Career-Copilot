export interface User {
  id: number;
  name: string;
  email: string;
  created_at: string;
  is_admin: boolean;
}

export interface SignupResponse {
  message: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user: DashboardUserStats;
}

export interface DashboardUserStats {
  id: number;
  name: string;
  email: string;
  is_admin: boolean;
}

export interface DashboardStatsData {
  total_applications: number;
  jobs_found?: number;
  skipped_jobs: number;
  saved_jobs?: number;
  applied_jobs?: number;
  tailored_resumes?: number;
  interviews: number;
  offers: number;
}

export interface DashboardStatsResponse {
  user: DashboardUserStats;
  stats: DashboardStatsData;
}
