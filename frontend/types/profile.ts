export interface ResumeDetails {
  id: number;
  user_id: number;
  file_name: string;
  file_path: string;
  file_type: string;
  file_size: number;
  uploaded_at: string;
  updated_at: string;
}

export interface ProjectData {
  name: string;
  description: string;
  technologies_used: string;
}

export interface CertificationData {
  name: string;
  issuing_organization: string;
  year: number;
}

export interface UserProfileData {
  id?: number;
  user_id?: number;
  full_name: string;
  email: string;
  phone: string;
  location: string;
  
  desired_role: string;
  years_experience: string;
  current_designation: string;
  current_company: string;
  
  degree: string;
  college: string;
  graduation_year: number;
  
  skills: string[];
  projects: ProjectData[];
  certifications: CertificationData[];
  
  // Career Goals
  desired_job_title: string;
  preferred_location: string;
  expected_salary: string;
  work_mode: string;
  max_applications_per_day: number;
  job_search_status: string;
  
  created_at?: string;
  updated_at?: string;
}

export interface CandidateProfileData {
  user_id: number;
  parsed_profile_json?: Record<string, unknown>;
  raw_resume_text?: string;
  name?: string;
  email?: string;
  phone?: string;
  location?: string;
  skills: unknown[];
  projects: unknown[];
  experience: unknown[];
  education: unknown[];
  certifications: unknown[];
  tools?: unknown[];
  languages?: unknown[];
  summary?: string;
  years_of_experience?: number;
  career_level?: string;
  updated_at?: string;
}
