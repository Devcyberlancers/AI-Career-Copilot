"use client";

import React, { useEffect, useMemo, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { fetchDashboardStats } from "@/services/auth";
import { DashboardStatsData } from "@/types/auth";
import { uploadResume, fetchMyResume, deleteMyResume } from "@/services/resume";
import { createProfile, fetchCandidateProfile, fetchMyProfile, updateProfile } from "@/services/profile";
import { CandidateProfileData, ResumeDetails, UserProfileData, ProjectData, CertificationData } from "@/types/profile";
import { discoverJobs, fetchPlatformStats, fetchUserJobs, isValidSupportedJobUrl, JOB_SOURCES, PlatformStat, updateJobStatus, Job, JobDiscoverySource, JobStatus, StoredJobSource } from "@/services/jobs";
import { downloadResumeFromUrl, previewTailoredResume, tailorResume, TailorResumeResponse } from "@/services/tailoring";

function matchScoreClasses(score: number) {
  if (score >= 90) return "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-300";
  if (score >= 75) return "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900/50 dark:bg-blue-950/30 dark:text-blue-300";
  if (score >= 60) return "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300";
  return "border-red-200 bg-red-50 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300";
}

function MatchScoreBadge({ score }: { score?: number | null }) {
  if (score === undefined || score === null) {
    return <span className="text-sm font-medium text-zinc-500">Not analyzed</span>;
  }
  return (
    <span className={`inline-flex rounded-md border px-2.5 py-1 text-sm font-bold ${matchScoreClasses(score)}`}>
      {Math.round(score)}%
    </span>
  );
}

function MatchList({ items, tone, emptyText }: { items: string[]; tone: "matched" | "missing"; emptyText: string }) {
  if (!items.length) {
    return <p className="text-xs text-zinc-500 dark:text-zinc-400">{emptyText}</p>;
  }
  const dotClass = tone === "matched" ? "bg-emerald-500" : "bg-red-500";
  return (
    <ul className="space-y-1.5">
      {items.map((item) => (
        <li key={item} className="flex items-center gap-2 text-xs text-zinc-700 dark:text-zinc-300">
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dotClass}`} />
          {item}
        </li>
      ))}
    </ul>
  );
}

export default function DashboardPage() {
  const { user, isAuthenticated, isLoading, logout } = useAuth();
  const router = useRouter();

  // Dashboard Stats State
  const [stats, setStats] = useState<DashboardStatsData>({
    total_applications: 0,
    skipped_jobs: 0,
    saved_jobs: 0,
    applied_jobs: 0,
    tailored_resumes: 0,
    interviews: 0,
    offers: 0,
  });
  const [fetchingStats, setFetchingStats] = useState(true);

  // Jobs UI State
  const [activeTab, setActiveTab] = useState<"profile" | "candidate" | "jobs">("profile");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [platformStats, setPlatformStats] = useState<PlatformStat[]>([]);
  const [fetchingJobs, setFetchingJobs] = useState(false);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [jobDiscoverySource, setJobDiscoverySource] = useState<JobDiscoverySource>("Naukri");
  const [jobSearchQuery, setJobSearchQuery] = useState("");
  const [jobStatusFilter, setJobStatusFilter] = useState<JobStatus | "All">("All");
  const [jobSourceTab, setJobSourceTab] = useState<JobDiscoverySource>("All");
  const [jobWorkModeFilter, setJobWorkModeFilter] = useState<"All" | "Remote" | "Hybrid" | "Onsite">("All");
  const [jobSortBy, setJobSortBy] = useState<"newest" | "oldest" | "company" | "match_score">("match_score");
  const [jobsPerPage, setJobsPerPage] = useState(10);
  const [jobsPage, setJobsPage] = useState(1);
  const [selectedJobIds, setSelectedJobIds] = useState<number[]>([]);
  const [updatingJobId, setUpdatingJobId] = useState<number | null>(null);
  const [discoveringJobs, setDiscoveringJobs] = useState(false);
  const [jobsMessage, setJobsMessage] = useState("");
  const [jobsError, setJobsError] = useState("");
  const [bulkUpdating, setBulkUpdating] = useState(false);
  const [tailoringJobId, setTailoringJobId] = useState<number | null>(null);
  const [tailoringStatusMessage, setTailoringStatusMessage] = useState("");
  const [tailoringResult, setTailoringResult] = useState<TailorResumeResponse | null>(null);
  const [tailoringResultJobId, setTailoringResultJobId] = useState<number | null>(null);
  const [dailyLimitNextAvailableAt, setDailyLimitNextAvailableAt] = useState<string | null>(null);
  const [dailyLimitRemainingSeconds, setDailyLimitRemainingSeconds] = useState(0);
  const isConnectedJobSource = jobDiscoverySource === "All" || JOB_SOURCES.includes(jobDiscoverySource as StoredJobSource);

  // Resume State
  const [resume, setResume] = useState<ResumeDetails | null>(null);
  const [fetchingResume, setFetchingResume] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [candidateProfile, setCandidateProfile] = useState<CandidateProfileData | null>(null);
  const [fetchingCandidateProfile, setFetchingCandidateProfile] = useState(false);

  // Profile State
  const [profile, setProfile] = useState<UserProfileData | null>(null);
  const [fetchingProfile, setFetchingProfile] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);

  // Wizard state: 1 for Resume, 2 for Profile Form
  const [wizardStep, setWizardStep] = useState<1 | 2>(1);
  const [wizardError, setWizardError] = useState("");
  const [wizardSuccess, setWizardSuccess] = useState("");

  // Refs
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Form Fields State
  const [formData, setFormData] = useState<UserProfileData>({
    full_name: "",
    email: "",
    phone: "",
    location: "",
    desired_role: "",
    years_experience: "",
    current_designation: "",
    current_company: "",
    degree: "",
    college: "",
    graduation_year: new Date().getFullYear(),
    skills: [],
    projects: [],
    certifications: [],
    desired_job_title: "",
    preferred_location: "",
    expected_salary: "",
    work_mode: "Remote",
    max_applications_per_day: 20,
    job_search_status: "Active",
  });

  // Dynamic Skill input state
  const [skillInput, setSkillInput] = useState("");

  // Dynamic Project input state
  const [projectInput, setProjectInput] = useState({
    name: "",
    description: "",
    technologies_used: "",
  });

  // Dynamic Certification input state
  const [certInput, setCertInput] = useState({
    name: "",
    issuing_organization: "",
    year: new Date().getFullYear(),
  });

  // Redirect if not authenticated
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [isLoading, isAuthenticated, router]);

  const loadJobs = async () => {
    if (!user) return;
    setFetchingJobs(true);
    setJobsError("");
    try {
      const [data, statsData] = await Promise.all([
        fetchUserJobs(),
        fetchPlatformStats(),
      ]);
      setJobs(data);
      setPlatformStats(statsData.sources || []);
      setSelectedJobIds([]);
    } catch (err) {
      console.error("Error loading user jobs:", err);
      setJobsError("Could not load jobs from the database. Please refresh or sign in again.");
    } finally {
      setFetchingJobs(false);
    }
  };

  const loadCandidateProfile = async () => {
    if (!user) return;
    setFetchingCandidateProfile(true);
    try {
      const data = await fetchCandidateProfile();
      setCandidateProfile(data);
    } catch {
      setCandidateProfile(null);
    } finally {
      setFetchingCandidateProfile(false);
    }
  };

  const handleUpdateJobStatus = async (jobId: number, newStatus: JobStatus) => {
    setUpdatingJobId(jobId);
    try {
      await updateJobStatus(jobId, newStatus);
      
      // Update local state
      setJobs(prevJobs =>
        prevJobs.map(job => (job.id === jobId ? { ...job, status: newStatus } : job))
      );
      setSelectedJob(prev => prev?.id === jobId ? { ...prev, status: newStatus } : prev);
      
      // Reload stats
      const statsData = await fetchDashboardStats();
      setStats(statsData.stats);
    } catch (err) {
      console.error("Error updating job status:", err);
    } finally {
      setUpdatingJobId(null);
    }
  };

  const handleBulkUpdateJobStatus = async (newStatus: JobStatus) => {
    if (selectedJobIds.length === 0) return;
    setBulkUpdating(true);
    setJobsError("");
    try {
      await Promise.all(selectedJobIds.map(jobId => updateJobStatus(jobId, newStatus)));
      setJobs(prevJobs =>
        prevJobs.map(job =>
          selectedJobIds.includes(job.id) ? { ...job, status: newStatus } : job
        )
      );
      setSelectedJobIds([]);
      const statsData = await fetchDashboardStats();
      setStats(statsData.stats);
      setJobsMessage(`${selectedJobIds.length} selected job${selectedJobIds.length === 1 ? "" : "s"} marked as ${newStatus}.`);
    } catch (err: any) {
      setJobsError(err.message || "Could not update selected jobs.");
    } finally {
      setBulkUpdating(false);
    }
  };

  const handleTailorResume = async (jobId: number) => {
    if (!user) return;
    const job = jobs.find(item => item.id === jobId) || (selectedJob?.id === jobId ? selectedJob : null);
    if (!job) {
      setJobsError("Could not find the selected job details.");
      return;
    }
    setTailoringJobId(jobId);
    setTailoringResult(null);
    setTailoringResultJobId(null);
    setTailoringStatusMessage("Generating tailored resume...");
    setJobsError("");
    setJobsMessage("");
    let statusTimer: number | null = null;
    try {
      const statusMessages = [
        "Generating tailored resume...",
        "AI optimizing resume...",
        "Generating PDF...",
      ];
      let statusIndex = 0;
      statusTimer = window.setInterval(() => {
        statusIndex = Math.min(statusIndex + 1, statusMessages.length - 1);
        setTailoringStatusMessage(statusMessages[statusIndex]);
      }, 2500);

      const result = await tailorResume({
        job_id: job.id,
        job_title: job.title,
        company: job.company,
        job_description: job.description || "No job description provided.",
      });
      if (statusTimer) window.clearInterval(statusTimer);
      const statsData = await fetchDashboardStats();
      setStats(statsData.stats);
      setTailoringResult(result);
      setTailoringResultJobId(jobId);
      setTailoringStatusMessage("Resume generated successfully");
      setJobsMessage("Resume generated successfully");
    } catch (err: any) {
      if (statusTimer) window.clearInterval(statusTimer);
      setJobsError(err.message || "Could not start resume tailoring. Please upload your master resume and try again.");
      setTailoringStatusMessage("");
    } finally {
      setTailoringJobId(null);
    }
  };

  const handlePreviewTailoredResume = async (resumeUrl?: string) => {
    if (!resumeUrl) {
      setJobsError("Preview URL is missing for this generated resume.");
      return;
    }
    try {
      await previewTailoredResume(resumeUrl);
    } catch (err: any) {
      setJobsError(err.message || "Could not preview tailored resume.");
    }
  };

  const handleDownloadTailoredResume = async (resumeUrl?: string, resumeId?: number) => {
    if (!resumeUrl) {
      setJobsError("Download URL is missing for this generated resume.");
      return;
    }
    try {
      await downloadResumeFromUrl(resumeUrl, `tailored_resume_${resumeId || "generated"}.pdf`);
    } catch (err: any) {
      setJobsError(err.message || "Could not download tailored resume.");
    }
  };

  const handleDiscoverJobs = async () => {
    setDiscoveringJobs(true);
    setJobsMessage("");
    setJobsError("");
    try {
      const result = await discoverJobs(jobDiscoverySource);
      if (!result.success && result.error === "DAILY_LIMIT_REACHED") {
        setDailyLimitNextAvailableAt(result.next_available_at || null);
        setDailyLimitRemainingSeconds(result.remaining_seconds || 0);
        setJobsError(
          `Daily Job Discovery Limit Reached. You have already discovered ${result.daily_limit || 20} jobs in the last 24 hours. Next search available: ${formatLimitTimestamp(result.next_available_at || null)}.`
        );
        return;
      }

      setDailyLimitNextAvailableAt(result.next_available_at || null);
      setDailyLimitRemainingSeconds(result.remaining_seconds || 0);
      await loadJobs();
      const statsData = await fetchDashboardStats();
      setStats(statsData.stats);
      const checkedJobs = result.jobs_found || 0;
      const storedJobs = result.jobs_stored || 0;
      const skippedJobs = result.jobs_skipped || 0;
      const quotaText = result.remaining_jobs !== undefined
        ? `${result.remaining_jobs} discovery slot${result.remaining_jobs === 1 ? "" : "s"} left in this 24-hour window.`
        : "";
      const storageText = storedJobs > 0
        ? `Stored ${storedJobs} new unique job${storedJobs === 1 ? "" : "s"}.`
        : `No new jobs were stored because ${skippedJobs || checkedJobs} matching job${(skippedJobs || checkedJobs) === 1 ? " was" : "s were"} already in your database.`;
      setJobsMessage(
        `Checked ${checkedJobs} ${jobDiscoverySource === "All" ? "multi-platform" : jobDiscoverySource} job${checkedJobs === 1 ? "" : "s"} for "${result.query || "your profile"}" (limit ${result.max_results || 20}). ${storageText} ${quotaText}`
      );
    } catch (err: any) {
      setJobsError(err.message || `Failed to fetch jobs from ${jobDiscoverySource}.`);
    } finally {
      setDiscoveringJobs(false);
    }
  };

  // Load stats, profile, and resume on mount
  const loadAllData = async () => {
    if (!isAuthenticated) return;

    // Load Jobs
    loadJobs();

    // Load Candidate Profile
    loadCandidateProfile();

    // Load Stats
    try {
      const statsData = await fetchDashboardStats();
      setStats(statsData.stats);
    } catch (err) {
      console.error("Error loading stats:", err);
    } finally {
      setFetchingStats(false);
    }

    // Load Resume
    try {
      const resumeData = await fetchMyResume();
      setResume(resumeData);
    } catch (err) {
      // 404 is normal if they haven't uploaded a resume yet
      console.log("No resume found or failed to fetch resume:", err);
    } finally {
      setFetchingResume(false);
    }

    // Load Profile
    try {
      const profileData = await fetchMyProfile();
      setProfile(profileData);
      // Pre-fill form fields
      setFormData({
        full_name: profileData.full_name || "",
        email: profileData.email || "",
        phone: profileData.phone || "",
        location: profileData.location || "",
        desired_role: profileData.desired_role || "",
        years_experience: profileData.years_experience || "",
        current_designation: profileData.current_designation || "",
        current_company: profileData.current_company || "",
        degree: profileData.degree || "",
        college: profileData.college || "",
        graduation_year: profileData.graduation_year || new Date().getFullYear(),
        skills: profileData.skills || [],
        projects: profileData.projects || [],
        certifications: profileData.certifications || [],
        desired_job_title: profileData.desired_job_title || "",
        preferred_location: profileData.preferred_location || "",
        expected_salary: profileData.expected_salary || "",
        work_mode: profileData.work_mode || "Remote",
        max_applications_per_day: profileData.max_applications_per_day ?? 20,
        job_search_status: profileData.job_search_status || "Active",
      });
    } catch (err) {
      // 404 is normal if profile setup is not yet complete
      console.log("No profile found or failed to fetch profile:", err);
    } finally {
      setFetchingProfile(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      loadAllData();
    }
  }, [isAuthenticated]);

  // Sync Form full_name and email with Auth User name and email if empty
  useEffect(() => {
    if (user && !formData.full_name && !formData.email) {
      setFormData(prev => ({
        ...prev,
        full_name: prev.full_name || user.name || "",
        email: prev.email || user.email || "",
      }));
    }
  }, [user, formData.full_name, formData.email]);

  // Format File Size
  const formatBytes = (bytes: number, decimals = 2) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
  };

  const formatCountdown = (totalSeconds: number) => {
    const seconds = Math.max(0, totalSeconds);
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = seconds % 60;
    if (hours > 0) return `${hours}h ${minutes}m`;
    if (minutes > 0) return `${minutes}m ${remainingSeconds}s`;
    return `${remainingSeconds}s`;
  };

  const formatLimitTimestamp = (timestamp: string | null) => {
    if (!timestamp) return "";
    return new Date(timestamp).toLocaleString();
  };

  const isDailyLimitActive = dailyLimitRemainingSeconds > 0;

  useEffect(() => {
    if (!dailyLimitNextAvailableAt) return;

    const updateCountdown = () => {
      const seconds = Math.max(
        0,
        Math.ceil((new Date(dailyLimitNextAvailableAt).getTime() - Date.now()) / 1000)
      );
      setDailyLimitRemainingSeconds(seconds);
      if (seconds <= 0) {
        setDailyLimitNextAvailableAt(null);
        setJobsError("");
      }
    };

    updateCountdown();
    const timer = window.setInterval(updateCountdown, 1000);
    return () => window.clearInterval(timer);
  }, [dailyLimitNextAvailableAt]);

  // Resume Upload Handler
  const handleResumeFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await uploadFile(file);
  };

  const uploadFile = async (file: File) => {
    setWizardError("");
    setWizardSuccess("");

    // Validate extension
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (ext !== "pdf" && ext !== "docx") {
      setWizardError("Invalid format. Only PDF and DOCX files are allowed.");
      return;
    }

    // Validate size (10MB)
    if (file.size > 10 * 1024 * 1024) {
      setWizardError("File is too large. Maximum size allowed is 10 MB.");
      return;
    }

    setIsUploading(true);
    setUploadProgress(10);

    // Simulate progress check
    const progressInterval = setInterval(() => {
      setUploadProgress(prev => {
        if (prev >= 90) {
          clearInterval(progressInterval);
          return 90;
        }
        return prev + 15;
      });
    }, 100);

    try {
      const data = await uploadResume(file);
      clearInterval(progressInterval);
      setUploadProgress(100);
      setResume(data);
      setTimeout(() => {
        loadCandidateProfile();
      }, 1500);
      setWizardSuccess("Resume uploaded successfully!");
      // Automatically advance to profile form
      setTimeout(() => {
        setWizardStep(2);
        setWizardSuccess("");
      }, 1000);
    } catch (err: any) {
      clearInterval(progressInterval);
      setWizardError(err.message || "Failed to upload resume.");
    } finally {
      setTimeout(() => {
        setIsUploading(false);
        setUploadProgress(0);
      }, 500);
    }
  };

  // Drag and Drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) {
      await uploadFile(file);
    }
  };

  // Resume Delete Handler
  const handleDeleteResume = async () => {
    if (!window.confirm("Are you sure you want to delete your resume?")) return;
    setWizardError("");
    setWizardSuccess("");
    try {
      await deleteMyResume();
      setResume(null);
      setWizardSuccess("Resume deleted successfully.");
      setWizardStep(1);
    } catch (err: any) {
      setWizardError(err.message || "Failed to delete resume.");
    }
  };

  // Skills input handlers
  const handleAddSkill = (e: React.KeyboardEvent | React.MouseEvent) => {
    if ("key" in e && e.key !== "Enter") return;
    e.preventDefault();
    const trimmed = skillInput.trim();
    if (trimmed && !formData.skills.includes(trimmed)) {
      setFormData(prev => ({
        ...prev,
        skills: [...prev.skills, trimmed],
      }));
      setSkillInput("");
    }
  };

  const handleRemoveSkill = (skillToRemove: string) => {
    setFormData(prev => ({
      ...prev,
      skills: prev.skills.filter(s => s !== skillToRemove),
    }));
  };

  // Projects input handlers
  const handleAddProject = (e: React.MouseEvent) => {
    e.preventDefault();
    if (!projectInput.name.trim() || !projectInput.description.trim()) {
      alert("Project Name and Description are required.");
      return;
    }
    const newProject: ProjectData = {
      name: projectInput.name.trim(),
      description: projectInput.description.trim(),
      technologies_used: projectInput.technologies_used.trim(),
    };
    setFormData(prev => ({
      ...prev,
      projects: [...prev.projects, newProject],
    }));
    setProjectInput({ name: "", description: "", technologies_used: "" });
  };

  const handleRemoveProject = (indexToRemove: number) => {
    setFormData(prev => ({
      ...prev,
      projects: prev.projects.filter((_, idx) => idx !== indexToRemove),
    }));
  };

  // Certifications input handlers
  const handleAddCert = (e: React.MouseEvent) => {
    e.preventDefault();
    if (!certInput.name.trim() || !certInput.issuing_organization.trim()) {
      alert("Certification Name and Issuing Organization are required.");
      return;
    }
    const newCert: CertificationData = {
      name: certInput.name.trim(),
      issuing_organization: certInput.issuing_organization.trim(),
      year: Number(certInput.year) || new Date().getFullYear(),
    };
    setFormData(prev => ({
      ...prev,
      certifications: [...prev.certifications, newCert],
    }));
    setCertInput({ name: "", issuing_organization: "", year: new Date().getFullYear() });
  };

  const handleRemoveCert = (indexToRemove: number) => {
    setFormData(prev => ({
      ...prev,
      certifications: prev.certifications.filter((_, idx) => idx !== indexToRemove),
    }));
  };

  // Form Submit Handler
  const handleFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setWizardError("");
    setWizardSuccess("");

    // Validate Required fields
    const required = [
      "full_name",
      "email",
      "phone",
      "location",
      "desired_role",
      "years_experience",
      "degree",
      "college",
      "graduation_year",
      "desired_job_title",
      "preferred_location",
      "work_mode",
    ];

    const missing = required.filter(field => !String((formData as any)[field]).trim());
    if (missing.length > 0) {
      setWizardError(`Please fill in all required fields. (Missing: ${missing.map(f => f.replace("_", " ")).join(", ")})`);
      return;
    }

    setSavingProfile(true);

    try {
      let savedProfile: UserProfileData;
      if (profile) {
        // Update profile
        savedProfile = await updateProfile(formData);
        setWizardSuccess("Profile updated successfully!");
      } else {
        // Create profile
        savedProfile = await createProfile(formData);
        setWizardSuccess("Profile setup completed successfully!");
      }
      setProfile(savedProfile);
      setTimeout(() => {
        loadCandidateProfile();
      }, 1500);
      setIsEditing(false);
      // Clean up success status after a delay
      setTimeout(() => {
        setWizardSuccess("");
      }, 3000);
    } catch (err: any) {
      setWizardError(err.message || "Failed to save profile.");
    } finally {
      setSavingProfile(false);
    }
  };

  const jobCounters = useMemo(() => {
    return jobs.reduce(
      (acc, job) => {
        acc.total += 1;
        if (job.status === "Discovered") acc.discovered += 1;
        if (job.status === "Saved") acc.saved += 1;
        if (job.status === "Applied") acc.applied += 1;
        if (job.status === "Skipped") acc.skipped += 1;
        return acc;
      },
      { total: 0, discovered: 0, saved: 0, applied: 0, skipped: 0 }
    );
  }, [jobs]);

  const platformCounts = useMemo(() => {
    const counts = new Map<StoredJobSource, { count: number; last_refresh_at?: string | null }>();
    platformStats.forEach((item) => counts.set(item.source, { count: item.count, last_refresh_at: item.last_refresh_at }));
    jobs.forEach((job) => {
      const source = (job.source || "Naukri") as StoredJobSource;
      const existing = counts.get(source) || { count: 0, last_refresh_at: null };
      counts.set(source, {
        count: Math.max(existing.count, 0) || jobs.filter((item) => (item.source || "Naukri") === source).length,
        last_refresh_at: existing.last_refresh_at,
      });
    });
    return counts;
  }, [jobs, platformStats]);

  const platformCards = useMemo(() => {
    return [
      { source: "All" as JobDiscoverySource, label: "Total Jobs", icon: "â—Ž", count: jobCounters.total, last_refresh_at: null },
      ...JOB_SOURCES.map((source) => {
        const stat = platformCounts.get(source);
        return {
          source,
          label: source,
          icon: source.slice(0, 1),
          count: stat?.count || 0,
          last_refresh_at: stat?.last_refresh_at || null,
        };
      }),
    ];
  }, [jobCounters.total, platformCounts]);

  const filteredJobs = useMemo(() => {
    const search = jobSearchQuery.trim().toLowerCase();
    return jobs
      .filter((job) => {
        const queryMatch =
          !search ||
          job.title.toLowerCase().includes(search) ||
          job.company.toLowerCase().includes(search) ||
          (job.location || "").toLowerCase().includes(search);
        const statusMatch = jobStatusFilter === "All" || job.status === jobStatusFilter;
        const sourceMatch = jobSourceTab === "All" || (job.source || "Naukri") === jobSourceTab;
        const workModeText = `${job.location || ""} ${job.description || ""}`.toLowerCase();
        const workModeMatch =
          jobWorkModeFilter === "All" ||
          (jobWorkModeFilter === "Remote" && (workModeText.includes("remote") || workModeText.includes("work from home") || workModeText.includes("wfh"))) ||
          (jobWorkModeFilter === "Hybrid" && workModeText.includes("hybrid")) ||
          (jobWorkModeFilter === "Onsite" && (workModeText.includes("onsite") || workModeText.includes("on-site") || workModeText.includes("office")));
        return queryMatch && statusMatch && sourceMatch && workModeMatch;
      })
      .sort((a, b) => {
        if (jobSortBy === "oldest") {
          return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
        }
        if (jobSortBy === "company") {
          return a.company.localeCompare(b.company);
        }
        if (jobSortBy === "match_score") {
          return (b.match_score ?? -1) - (a.match_score ?? -1);
        }
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      });
  }, [jobs, jobSearchQuery, jobSortBy, jobStatusFilter, jobSourceTab, jobWorkModeFilter]);

  const totalJobPages = Math.max(1, Math.ceil(filteredJobs.length / jobsPerPage));
  const paginatedJobs = useMemo(() => {
    const start = (jobsPage - 1) * jobsPerPage;
    return filteredJobs.slice(start, start + jobsPerPage);
  }, [filteredJobs, jobsPage, jobsPerPage]);

  useEffect(() => {
    setJobsPage(1);
    setSelectedJobIds([]);
  }, [jobSearchQuery, jobStatusFilter, jobSourceTab, jobWorkModeFilter, jobSortBy, jobsPerPage]);

  useEffect(() => {
    if (jobsPage > totalJobPages) {
      setJobsPage(totalJobPages);
    }
  }, [jobsPage, totalJobPages]);

  const statusBadgeClass = (statusValue: string) => {
    if (statusValue === "Discovered") return "bg-blue-50 text-blue-700 dark:bg-blue-950/30 dark:text-blue-300";
    if (statusValue === "Saved") return "bg-purple-50 text-purple-700 dark:bg-purple-950/30 dark:text-purple-300";
    if (statusValue === "Applied") return "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300";
    if (statusValue === "Skipped") return "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
    return "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
  };

  const candidateItemText = (item: unknown) => {
    if (typeof item === "string") return item;
    if (typeof item === "number") return String(item);
    if (item && typeof item === "object") {
      const record = item as Record<string, unknown>;
      const title = record.name || record.title || record.role || record.degree || record.company;
      const description = record.description || record.summary || record.institution || record.organization;
      return [title, description].filter(Boolean).join(" - ") || JSON.stringify(item);
    }
    return "";
  };

  const hasCandidateProfile = Boolean(
    candidateProfile &&
      (
        candidateProfile.summary ||
        candidateProfile.skills?.length ||
        candidateProfile.projects?.length ||
        candidateProfile.experience?.length ||
        candidateProfile.education?.length ||
        candidateProfile.certifications?.length
      )
  );

  const resumeUploaded = Boolean(resume);
  const resumeParsed = Boolean(candidateProfile?.raw_resume_text || hasCandidateProfile);

  const toggleSelectedJob = (jobId: number) => {
    setSelectedJobIds(prev =>
      prev.includes(jobId) ? prev.filter(id => id !== jobId) : [...prev, jobId]
    );
  };

  const allPageJobsSelected = paginatedJobs.length > 0 && paginatedJobs.every(job => selectedJobIds.includes(job.id));

  const toggleSelectPageJobs = () => {
    if (allPageJobsSelected) {
      setSelectedJobIds(prev => prev.filter(id => !paginatedJobs.some(job => job.id === id)));
      return;
    }
    setSelectedJobIds(prev => Array.from(new Set([...prev, ...paginatedJobs.map(job => job.id)])));
  };

  // Helper to check if session loading
  if (isLoading || (!isAuthenticated && !isLoading)) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-950">
        <div className="flex flex-col items-center gap-4">
          <svg className="animate-spin h-10 w-10 text-indigo-600" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <span className="text-sm font-medium text-zinc-600 dark:text-zinc-400">Loading session...</span>
        </div>
      </div>
    );
  }

  // Determine view mode
  // If user profile is not fetched and not currently editing, we display Wizard
  const showWizard = !profile || isEditing;

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950 flex flex-col transition-colors duration-200">
      {/* Header */}
      <header className="sticky top-0 z-40 w-full border-b border-zinc-200 bg-white/80 backdrop-blur-md dark:border-zinc-800 dark:bg-zinc-950/80">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <div className="flex items-center gap-2">
            <svg className="h-8 w-8 text-indigo-600 dark:text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <span className="text-xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
              AI Career Copilot
            </span>
            <span className="ml-2 rounded-full bg-zinc-100 dark:bg-zinc-800 px-2 py-0.5 text-xs font-semibold text-zinc-500 dark:text-zinc-400">
              Dashboard
            </span>
          </div>
          <div className="flex items-center gap-4">
            <nav className="hidden items-center gap-3 text-sm text-zinc-600 dark:text-zinc-400 lg:flex">
              <Link href="/usage" className="hover:text-indigo-500">Usage</Link>
              <Link href="/settings/notifications" className="hover:text-indigo-500">Settings</Link>
              <Link href="/email/history" className="hover:text-indigo-500">Emails</Link>
            </nav>
            <span className="hidden md:inline text-sm text-zinc-600 dark:text-zinc-400">
              Logged in as <span className="font-semibold text-zinc-900 dark:text-zinc-50">{user?.email}</span>
            </span>

            <Button variant="ghost" size="sm" onClick={logout}>
              Sign Out
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8 space-y-8">
        {/* Welcome Banner */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
              Welcome, {user?.name || "User"}
            </h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              Build your professional footprint and job search preferences.
            </p>
          </div>
        </div>

        {/* Statistics Grid */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card className="hover:shadow-md transition-shadow">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="text-sm font-medium text-zinc-500 dark:text-zinc-400">Jobs Found</span>
              <svg className="h-4 w-4 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{fetchingStats ? "..." : stats.jobs_found ?? stats.total_applications}</div>
              <p className="text-xs text-zinc-400 mt-1">Found by discovery engine</p>
            </CardContent>
          </Card>

          <Card className="hover:shadow-md transition-shadow">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="text-sm font-medium text-zinc-500 dark:text-zinc-400">Saved Jobs</span>
              <svg className="h-4 w-4 text-teal-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
              </svg>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{fetchingStats ? "..." : stats.saved_jobs ?? stats.interviews}</div>
              <p className="text-xs text-zinc-400 mt-1">Starred for later action</p>
            </CardContent>
          </Card>

          <Card className="hover:shadow-md transition-shadow">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="text-sm font-medium text-zinc-500 dark:text-zinc-400">Applied Jobs</span>
              <svg className="h-4 w-4 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
              </svg>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{fetchingStats ? "..." : stats.applied_jobs ?? stats.offers}</div>
              <p className="text-xs text-zinc-400 mt-1">Applications submitted</p>
            </CardContent>
          </Card>

          <Card className="hover:shadow-md transition-shadow">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="text-sm font-medium text-zinc-500 dark:text-zinc-400">Tailored Resumes</span>
              <svg className="h-4 w-4 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428A8 8 0 118.572 4.572M15 10h5m0 0v5m0-5l-8 8" />
              </svg>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{fetchingStats ? "..." : stats.tailored_resumes ?? 0}</div>
              <p className="text-xs text-zinc-400 mt-1">Optimized resume versions</p>
            </CardContent>
          </Card>
        </div>

        {/* Global Notifications */}
        {wizardError && (
          <div className="rounded-lg bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400 p-4 text-sm font-medium border border-red-200 dark:border-red-900/40">
            {wizardError}
          </div>
        )}
        {wizardSuccess && (
          <div className="rounded-lg bg-emerald-50 dark:bg-emerald-950/20 text-emerald-600 dark:text-emerald-400 p-4 text-sm font-medium border border-emerald-200 dark:border-emerald-900/40 animate-pulse">
            {wizardSuccess}
          </div>
        )}

        {/* Main Work Area */}
        {fetchingProfile || fetchingResume ? (
          <Card className="p-8 flex flex-col items-center justify-center min-h-[300px]">
            <svg className="animate-spin h-8 w-8 text-indigo-600 mb-2" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            <span className="text-zinc-500 dark:text-zinc-400 text-sm">Fetching profile details...</span>
          </Card>
        ) : showWizard ? (
          /* ================= STEP-BY-STEP SETUP WIZARD ================= */
          <Card className="border border-zinc-200 dark:border-zinc-800 shadow-md">
            <CardHeader className="border-b border-zinc-200 dark:border-zinc-800 pb-4">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                <div>
                  <CardTitle className="text-xl font-bold text-zinc-900 dark:text-zinc-50">
                    {profile ? "Edit Your Profile & Preferences" : "Step-by-Step Profile Wizard"}
                  </CardTitle>
                  <CardDescription>
                    Complete these steps to build your career footprint.
                  </CardDescription>
                </div>
                {/* Steps tracker indicators */}
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setWizardStep(1)}
                    className={`flex items-center justify-center h-8 px-3 rounded-full text-xs font-semibold transition-all ${
                      wizardStep === 1
                        ? "bg-indigo-600 text-white shadow"
                        : "bg-zinc-100 hover:bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                    }`}
                  >
                    1. Upload Resume
                  </button>
                  <span className="text-zinc-300 dark:text-zinc-700">â†’</span>
                  <button
                    onClick={() => {
                      if (!resume && !profile) {
                        setWizardError("Please upload a resume first, or complete it later.");
                      }
                      setWizardStep(2);
                    }}
                    className={`flex items-center justify-center h-8 px-3 rounded-full text-xs font-semibold transition-all ${
                      wizardStep === 2
                        ? "bg-indigo-600 text-white shadow"
                        : "bg-zinc-100 hover:bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                    }`}
                  >
                    2. Profile & Goals
                  </button>
                </div>
              </div>
            </CardHeader>

            <CardContent className="p-6 md:p-8">
              {/* --- STEP 1: RESUME UPLOAD --- */}
              {wizardStep === 1 && (
                <div className="space-y-6">
                  <div>
                    <h3 className="text-lg font-semibold text-zinc-800 dark:text-zinc-200 mb-1">
                      Upload your latest CV / Resume
                    </h3>
                    <p className="text-sm text-zinc-500 dark:text-zinc-400">
                      Upload a PDF or DOCX file under 10MB.
                    </p>
                  </div>

                  {/* Drop zone */}
                  <div
                    onDragOver={handleDragOver}
                    onDrop={handleDrop}
                    onClick={() => fileInputRef.current?.click()}
                    className={`border-dashed border-2 rounded-xl flex flex-col items-center justify-center p-10 cursor-pointer transition-all ${
                      isUploading
                        ? "border-indigo-400 bg-indigo-50/20 dark:bg-indigo-950/10 pointer-events-none"
                        : "border-zinc-300 hover:border-indigo-500 hover:bg-zinc-50/50 dark:border-zinc-800 dark:hover:border-indigo-500 dark:hover:bg-zinc-900/10"
                    }`}
                  >
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf,.docx"
                      onChange={handleResumeFileChange}
                      className="hidden"
                    />

                    {isUploading ? (
                      <div className="flex flex-col items-center space-y-3 w-full max-w-xs">
                        <svg className="animate-spin h-10 w-10 text-indigo-600" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        <div className="w-full bg-zinc-200 rounded-full h-2 dark:bg-zinc-700 overflow-hidden">
                          <div
                            className="bg-indigo-600 h-2 rounded-full transition-all duration-300"
                            style={{ width: `${uploadProgress}%` }}
                          />
                        </div>
                        <span className="text-sm font-semibold text-indigo-600">
                          Uploading your resume ({uploadProgress}%)
                        </span>
                      </div>
                    ) : resume ? (
                      <div className="flex flex-col items-center space-y-3">
                        <div className="p-3 bg-emerald-100 dark:bg-emerald-950/40 rounded-full">
                          <svg className="h-8 w-8 text-emerald-600 dark:text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                        </div>
                        <div className="text-center">
                          <p className="font-semibold text-zinc-900 dark:text-zinc-100 max-w-sm truncate">
                            {resume.file_name}
                          </p>
                          <p className="text-xs text-zinc-500 dark:text-zinc-400">
                            {formatBytes(resume.file_size)} â€¢ {resume.file_type.split("/")[1]?.toUpperCase() || "PDF"}
                          </p>
                          <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">
                            Uploaded on {new Date(resume.uploaded_at).toLocaleDateString()}
                          </p>
                        </div>
                      </div>
                    ) : (
                      <div className="text-center space-y-2">
                        <div className="mx-auto flex justify-center text-zinc-400">
                          <svg className="h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                          </svg>
                        </div>
                        <p className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                          Drag and drop your resume file here
                        </p>
                        <p className="text-xs text-zinc-400">
                          or click to browse from files (PDF/DOCX max 10MB)
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Actions for Step 1 */}
                  <div className="flex justify-between items-center pt-4 border-t border-zinc-100 dark:border-zinc-800">
                    <div>
                      {resume && (
                        <Button
                          variant="ghost"
                          className="text-red-500 hover:text-red-600"
                          onClick={handleDeleteResume}
                        >
                          Delete Current Resume
                        </Button>
                      )}
                    </div>
                    <div className="flex gap-3">
                      {profile && (
                        <Button variant="outline" onClick={() => setIsEditing(false)}>
                          Cancel
                        </Button>
                      )}
                      <Button
                        variant="default"
                        onClick={() => setWizardStep(2)}
                      >
                        Next: Profile Details
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {/* --- STEP 2: PROFILE FORM & GOALS --- */}
              {wizardStep === 2 && (
                <form onSubmit={handleFormSubmit} className="space-y-8">
                  {/* Category 1: Personal Info */}
                  <div className="space-y-4">
                    <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50 border-b border-zinc-100 dark:border-zinc-800 pb-2">
                      1. Contact & Personal Details
                    </h3>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div className="space-y-1">
                        <Label htmlFor="full_name">Full Name <span className="text-red-500">*</span></Label>
                        <Input
                          id="full_name"
                          value={formData.full_name}
                          onChange={e => setFormData({ ...formData, full_name: e.target.value })}
                          placeholder="e.g. John Doe"
                          required
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="email">Email <span className="text-red-500">*</span></Label>
                        <Input
                          id="email"
                          type="email"
                          value={formData.email}
                          onChange={e => setFormData({ ...formData, email: e.target.value })}
                          placeholder="e.g. john@example.com"
                          required
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="phone">Phone Number <span className="text-red-500">*</span></Label>
                        <Input
                          id="phone"
                          value={formData.phone}
                          onChange={e => setFormData({ ...formData, phone: e.target.value })}
                          placeholder="e.g. +1 234 567 8900"
                          required
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="location">Location (City, Country) <span className="text-red-500">*</span></Label>
                        <Input
                          id="location"
                          value={formData.location}
                          onChange={e => setFormData({ ...formData, location: e.target.value })}
                          placeholder="e.g. New York, USA"
                          required
                        />
                      </div>
                    </div>
                  </div>

                  {/* Category 2: Professional Profile */}
                  <div className="space-y-4">
                    <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50 border-b border-zinc-100 dark:border-zinc-800 pb-2">
                      2. Professional Summary
                    </h3>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div className="space-y-1">
                        <Label htmlFor="desired_role">Desired Job Role <span className="text-red-500">*</span></Label>
                        <Input
                          id="desired_role"
                          value={formData.desired_role}
                          onChange={e => setFormData({ ...formData, desired_role: e.target.value })}
                          placeholder="e.g. Senior Frontend Engineer"
                          required
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="years_experience">Years of Experience <span className="text-red-500">*</span></Label>
                        <Input
                          id="years_experience"
                          value={formData.years_experience}
                          onChange={e => setFormData({ ...formData, years_experience: e.target.value })}
                          placeholder="e.g. 5+ Years"
                          required
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="current_designation">Current Designation</Label>
                        <Input
                          id="current_designation"
                          value={formData.current_designation}
                          onChange={e => setFormData({ ...formData, current_designation: e.target.value })}
                          placeholder="e.g. Software Engineer"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="current_company">Current Company</Label>
                        <Input
                          id="current_company"
                          value={formData.current_company}
                          onChange={e => setFormData({ ...formData, current_company: e.target.value })}
                          placeholder="e.g. Tech Corp"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Category 3: Education */}
                  <div className="space-y-4">
                    <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50 border-b border-zinc-100 dark:border-zinc-800 pb-2">
                      3. Academic Background
                    </h3>
                    <div className="grid gap-4 sm:grid-cols-3">
                      <div className="space-y-1">
                        <Label htmlFor="degree">Degree <span className="text-red-500">*</span></Label>
                        <Input
                          id="degree"
                          value={formData.degree}
                          onChange={e => setFormData({ ...formData, degree: e.target.value })}
                          placeholder="e.g. B.S. in Computer Science"
                          required
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="college">College/University <span className="text-red-500">*</span></Label>
                        <Input
                          id="college"
                          value={formData.college}
                          onChange={e => setFormData({ ...formData, college: e.target.value })}
                          placeholder="e.g. MIT"
                          required
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="graduation_year">Graduation Year <span className="text-red-500">*</span></Label>
                        <Input
                          id="graduation_year"
                          type="number"
                          value={formData.graduation_year || ""}
                          onChange={e => setFormData({ ...formData, graduation_year: Number(e.target.value) })}
                          placeholder="e.g. 2024"
                          required
                        />
                      </div>
                    </div>
                  </div>

                  {/* Category 4: Skills - Tag generator */}
                  <div className="space-y-4">
                    <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50 border-b border-zinc-100 dark:border-zinc-800 pb-2">
                      4. Core Skills & Technologies
                    </h3>
                    <div className="space-y-3">
                      <Label htmlFor="skills_input">Add Skills (Press Enter or click Add)</Label>
                      <div className="flex gap-2">
                        <Input
                          id="skills_input"
                          value={skillInput}
                          onChange={e => setSkillInput(e.target.value)}
                          onKeyDown={handleAddSkill}
                          placeholder="e.g. React, TypeScript, Node.js"
                        />
                        <Button type="button" variant="secondary" onClick={handleAddSkill}>
                          Add
                        </Button>
                      </div>
                      {/* Skill Tags */}
                      <div className="flex flex-wrap gap-2 pt-1">
                        {formData.skills.map(skill => (
                          <span
                            key={skill}
                            className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1 text-sm font-semibold text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-900/30"
                          >
                            {skill}
                            <button
                              type="button"
                              onClick={() => handleRemoveSkill(skill)}
                              className="text-indigo-500 hover:text-indigo-800 focus:outline-none text-xs font-bold"
                            >
                              âœ•
                            </button>
                          </span>
                        ))}
                        {formData.skills.length === 0 && (
                          <span className="text-xs text-zinc-400">No skills added yet. Type and add some!</span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Category 5: Projects */}
                  <div className="space-y-4">
                    <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50 border-b border-zinc-100 dark:border-zinc-800 pb-2">
                      5. Notable Projects
                    </h3>
                    {/* Add Project Form */}
                    <div className="grid gap-3 p-4 border border-zinc-200 dark:border-zinc-800 rounded-lg bg-zinc-50/50 dark:bg-zinc-900/10">
                      <div className="grid gap-2 sm:grid-cols-2">
                        <div className="space-y-1">
                          <Label htmlFor="project_name">Project Name</Label>
                          <Input
                            id="project_name"
                            value={projectInput.name}
                            onChange={e => setProjectInput({ ...projectInput, name: e.target.value })}
                            placeholder="e.g. AI Portfolio Builder"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor="project_tech">Technologies Used</Label>
                          <Input
                            id="project_tech"
                            value={projectInput.technologies_used}
                            onChange={e => setProjectInput({ ...projectInput, technologies_used: e.target.value })}
                            placeholder="e.g. React, Next.js, FastAPI"
                          />
                        </div>
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="project_desc">Description</Label>
                        <textarea
                          id="project_desc"
                          rows={2}
                          value={projectInput.description}
                          onChange={e => setProjectInput({ ...projectInput, description: e.target.value })}
                          placeholder="Brief description of project achievements..."
                          className="flex w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-50"
                        />
                      </div>
                      <div className="flex justify-end pt-1">
                        <Button type="button" variant="outline" size="sm" onClick={handleAddProject}>
                          Add Project to List
                        </Button>
                      </div>
                    </div>

                    {/* Project List */}
                    <div className="space-y-3">
                      {formData.projects.map((proj, idx) => (
                        <div
                          key={idx}
                          className="flex justify-between items-start p-4 border border-zinc-200 dark:border-zinc-800 rounded-lg hover:shadow-sm"
                        >
                          <div className="space-y-1">
                            <h4 className="font-semibold text-zinc-900 dark:text-zinc-50">{proj.name}</h4>
                            <p className="text-xs text-indigo-600 dark:text-indigo-400 font-mono">
                              Tech: {proj.technologies_used}
                            </p>
                            <p className="text-sm text-zinc-600 dark:text-zinc-400">{proj.description}</p>
                          </div>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="text-red-500 hover:text-red-600"
                            onClick={() => handleRemoveProject(idx)}
                          >
                            Remove
                          </Button>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Category 6: Certifications */}
                  <div className="space-y-4">
                    <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50 border-b border-zinc-100 dark:border-zinc-800 pb-2">
                      6. Professional Certifications
                    </h3>
                    <div className="grid gap-3 p-4 border border-zinc-200 dark:border-zinc-800 rounded-lg bg-zinc-50/50 dark:bg-zinc-900/10">
                      <div className="grid gap-2 sm:grid-cols-3">
                        <div className="space-y-1">
                          <Label htmlFor="cert_name">Certification Name</Label>
                          <Input
                            id="cert_name"
                            value={certInput.name}
                            onChange={e => setCertInput({ ...certInput, name: e.target.value })}
                            placeholder="e.g. AWS Certified Solutions Architect"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor="cert_org">Issuing Organization</Label>
                          <Input
                            id="cert_org"
                            value={certInput.issuing_organization}
                            onChange={e => setCertInput({ ...certInput, issuing_organization: e.target.value })}
                            placeholder="e.g. Cloud Platforms"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor="cert_year">Year Received</Label>
                          <Input
                            id="cert_year"
                            type="number"
                            value={certInput.year || ""}
                            onChange={e => setCertInput({ ...certInput, year: Number(e.target.value) })}
                            placeholder="e.g. 2023"
                          />
                        </div>
                      </div>
                      <div className="flex justify-end pt-1">
                        <Button type="button" variant="outline" size="sm" onClick={handleAddCert}>
                          Add Certification to List
                        </Button>
                      </div>
                    </div>

                    {/* Certification List */}
                    <div className="space-y-3">
                      {formData.certifications.map((c, idx) => (
                        <div
                          key={idx}
                          className="flex justify-between items-center p-4 border border-zinc-200 dark:border-zinc-800 rounded-lg hover:shadow-sm"
                        >
                          <div>
                            <h4 className="font-semibold text-zinc-900 dark:text-zinc-50">{c.name}</h4>
                            <p className="text-sm text-zinc-600 dark:text-zinc-400">
                              Issued by {c.issuing_organization} ({c.year})
                            </p>
                          </div>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="text-red-500 hover:text-red-600"
                            onClick={() => handleRemoveCert(idx)}
                          >
                            Remove
                          </Button>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Category 7: Career Goals */}
                  <div className="space-y-4">
                    <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50 border-b border-zinc-100 dark:border-zinc-800 pb-2">
                      7. Target Career Goals & Preferences
                    </h3>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div className="space-y-1">
                        <Label htmlFor="desired_job_title">Desired Job Title <span className="text-red-500">*</span></Label>
                        <Input
                          id="desired_job_title"
                          value={formData.desired_job_title}
                          onChange={e => setFormData({ ...formData, desired_job_title: e.target.value })}
                          placeholder="e.g. Tech Lead or Principal Engineer"
                          required
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="preferred_location">Preferred Location <span className="text-red-500">*</span></Label>
                        <Input
                          id="preferred_location"
                          value={formData.preferred_location}
                          onChange={e => setFormData({ ...formData, preferred_location: e.target.value })}
                          placeholder="e.g. Remote / San Francisco, CA"
                          required
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="expected_salary">Expected Annual Salary (Optional)</Label>
                        <Input
                          id="expected_salary"
                          value={formData.expected_salary}
                          onChange={e => setFormData({ ...formData, expected_salary: e.target.value })}
                          placeholder="e.g. $140,000 - $160,000"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="work_mode">Preferred Work Mode <span className="text-red-500">*</span></Label>
                        <select
                          id="work_mode"
                          value={formData.work_mode}
                          onChange={e => setFormData({ ...formData, work_mode: e.target.value })}
                          className="flex h-10 w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-50"
                        >
                          <option value="Remote">Remote</option>
                          <option value="Hybrid">Hybrid</option>
                          <option value="Onsite">Onsite</option>
                        </select>
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="max_applications">Max Auto-Applications Per Day</Label>
                        <Input
                          id="max_applications"
                          type="number"
                          value={formData.max_applications_per_day}
                          onChange={e => setFormData({ ...formData, max_applications_per_day: Number(e.target.value) })}
                          min={1}
                          max={100}
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="search_status">Job Search Status</Label>
                        <select
                          id="search_status"
                          value={formData.job_search_status}
                          onChange={e => setFormData({ ...formData, job_search_status: e.target.value })}
                          className="flex h-10 w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-50"
                        >
                          <option value="Active">Active (Apply to Matching Jobs)</option>
                          <option value="Paused">Paused (Do not apply automatically)</option>
                        </select>
                      </div>
                    </div>
                  </div>

                  {/* Actions for Step 2 */}
                  <div className="flex justify-between items-center pt-6 border-t border-zinc-200 dark:border-zinc-800">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setWizardStep(1)}
                    >
                      Back to Resume
                    </Button>
                    <div className="flex gap-3">
                      {profile && (
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => setIsEditing(false)}
                        >
                          Cancel
                        </Button>
                      )}
                      <Button
                        type="submit"
                        variant="default"
                        isLoading={savingProfile}
                      >
                        {profile ? "Save Updates" : "Complete Setup"}
                      </Button>
                    </div>
                  </div>
                </form>
              )}
            </CardContent>
          </Card>
        ) : (
          /* ================= SUMMARY VIEW ================= */
          <div className="space-y-6">
            {/* Tab navigation */}
            <div className="flex border-b border-zinc-200 dark:border-zinc-800">
              <button
                className={`py-2.5 px-4 font-semibold text-sm border-b-2 transition-colors ${
                  activeTab === "profile"
                    ? "border-indigo-600 text-indigo-600 dark:border-indigo-500 dark:text-indigo-400 font-bold"
                    : "border-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
                }`}
                onClick={() => setActiveTab("profile")}
              >
                Profile & Goals
              </button>
              <button
                className={`py-2.5 px-4 font-semibold text-sm border-b-2 transition-colors ${
                  activeTab === "jobs"
                    ? "border-indigo-600 text-indigo-600 dark:border-indigo-500 dark:text-indigo-400 font-bold"
                    : "border-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
                }`}
                onClick={() => {
                  setActiveTab("jobs");
                  loadJobs();
                }}
              >
                Discovered Jobs
              </button>
              <button
                className={`py-2.5 px-4 font-semibold text-sm border-b-2 transition-colors ${
                  activeTab === "candidate"
                    ? "border-indigo-600 text-indigo-600 dark:border-indigo-500 dark:text-indigo-400 font-bold"
                    : "border-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
                }`}
                onClick={() => {
                  setActiveTab("candidate");
                  loadCandidateProfile();
                }}
              >
                Candidate Profile
              </button>
              <Link
                href="/tailored-resumes"
                className="py-2.5 px-4 font-semibold text-sm border-b-2 border-transparent text-zinc-500 transition-colors hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
              >
                My Tailored Resumes
              </Link>
            </div>

            {activeTab === "profile" ? (
              <div className="grid gap-6 lg:grid-cols-3">
                {/* Left Hand side: Primary info and actions */}
                <div className="lg:col-span-1 space-y-6">
                  {/* Profile Card Summary */}
                  <Card className="border border-zinc-200 dark:border-zinc-800 shadow-sm relative overflow-hidden">
                    <div className="h-2 bg-indigo-600 w-full absolute top-0 left-0" />
                    <CardHeader className="text-center pb-2 pt-8">
                      <div className="h-20 w-20 bg-indigo-100 dark:bg-indigo-950 rounded-full flex items-center justify-center mx-auto text-2xl font-bold text-indigo-700 dark:text-indigo-400">
                        {profile.full_name.split(" ").map(n => n[0]).join("").toUpperCase()}
                      </div>
                      <CardTitle className="text-xl font-bold mt-4 text-zinc-900 dark:text-zinc-50">
                        {profile.full_name}
                      </CardTitle>
                      <CardDescription className="font-medium text-indigo-600 dark:text-indigo-400">
                        {profile.desired_role}
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4 pt-4 border-t border-zinc-100 dark:border-zinc-800/80">
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-zinc-400">Location:</span>
                          <span className="font-semibold text-zinc-800 dark:text-zinc-200">{profile.location}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-zinc-400">Experience:</span>
                          <span className="font-semibold text-zinc-800 dark:text-zinc-200">{profile.years_experience}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-zinc-400">Email:</span>
                          <span className="font-semibold text-zinc-800 dark:text-zinc-200 break-all">{profile.email}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-zinc-400">Phone:</span>
                          <span className="font-semibold text-zinc-800 dark:text-zinc-200">{profile.phone}</span>
                        </div>
                        {profile.current_designation && (
                          <div className="flex justify-between">
                            <span className="text-zinc-400">Current Designation:</span>
                            <span className="font-semibold text-zinc-800 dark:text-zinc-200">{profile.current_designation}</span>
                          </div>
                        )}
                        {profile.current_company && (
                          <div className="flex justify-between">
                            <span className="text-zinc-400">Company:</span>
                            <span className="font-semibold text-zinc-800 dark:text-zinc-200">{profile.current_company}</span>
                          </div>
                        )}
                      </div>

                      <div className="pt-2">
                        <Button
                          variant="outline"
                          className="w-full"
                          onClick={() => {
                            setIsEditing(true);
                            setWizardStep(2);
                          }}
                        >
                          Edit Profile Info
                        </Button>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Resume Card Summary */}
                  <Card className="border border-zinc-200 dark:border-zinc-800 shadow-sm">
                    <CardHeader>
                      <CardTitle className="text-lg">Uploaded Resume</CardTitle>
                      <CardDescription>Verify or update your profile document.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {resume ? (
                        <div className="space-y-3">
                          <div className="flex items-center gap-3 p-3 bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg">
                            <svg className="h-8 w-8 text-indigo-600 dark:text-indigo-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                            <div className="overflow-hidden">
                              <p className="font-semibold text-sm text-zinc-900 dark:text-zinc-50 truncate" title={resume.file_name}>
                                {resume.file_name}
                              </p>
                              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                                {formatBytes(resume.file_size)} â€¢ {resume.file_type.split("/")[1]?.toUpperCase() || "PDF"}
                              </p>
                            </div>
                          </div>
                          <div className="flex gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              className="flex-1"
                              onClick={() => {
                                setIsEditing(true);
                                setWizardStep(1);
                              }}
                            >
                              Replace File
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-red-500 hover:text-red-650"
                              onClick={handleDeleteResume}
                            >
                              Remove
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="text-center p-6 border border-dashed border-zinc-300 dark:border-zinc-800 rounded-lg space-y-2">
                          <p className="text-xs text-zinc-500">No resume uploaded.</p>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setIsEditing(true);
                              setWizardStep(1);
                            }}
                          >
                            Upload Resume Now
                          </Button>
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  <Card className="border border-zinc-200 dark:border-zinc-800 shadow-sm">
                    <CardHeader>
                      <CardTitle className="text-lg">Resume Intelligence</CardTitle>
                      <CardDescription>Parsing status for your latest resume.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm">
                      {[
                        ["Resume Uploaded", resumeUploaded],
                        ["Resume Parsed", resumeParsed],
                        ["Candidate Profile Generated", hasCandidateProfile],
                      ].map(([label, done]) => (
                        <div key={label as string} className="flex items-center justify-between rounded-lg bg-zinc-50 px-3 py-2 dark:bg-zinc-900">
                          <span className="font-medium text-zinc-700 dark:text-zinc-300">{label as string}</span>
                          <span className={done ? "text-emerald-600 dark:text-emerald-400" : "text-zinc-400"}>
                            {done ? "Done" : "Pending"}
                          </span>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                </div>

                {/* Right hand side: Large view of education, skills, projects, certifications, goals */}
                <div className="lg:col-span-2 space-y-6">
                  {/* Career Goals & Settings */}
                  <Card className="border border-zinc-200 dark:border-zinc-800 shadow-sm">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-lg font-bold text-zinc-900 dark:text-zinc-50">
                        Career Goals & Job Preferences
                      </CardTitle>
                      <CardDescription>Target job title and system rules.</CardDescription>
                    </CardHeader>
                    <CardContent className="grid gap-4 sm:grid-cols-2 pt-2 text-sm">
                      <div className="flex justify-between p-2.5 rounded-lg bg-zinc-50 dark:bg-zinc-900">
                        <span className="text-zinc-500">Desired Job Title</span>
                        <span className="font-semibold text-zinc-900 dark:text-zinc-50">{profile.desired_job_title}</span>
                      </div>
                      <div className="flex justify-between p-2.5 rounded-lg bg-zinc-50 dark:bg-zinc-900">
                        <span className="text-zinc-500">Preferred Location</span>
                        <span className="font-semibold text-zinc-900 dark:text-zinc-50">{profile.preferred_location}</span>
                      </div>
                      <div className="flex justify-between p-2.5 rounded-lg bg-zinc-50 dark:bg-zinc-900">
                        <span className="text-zinc-500">Work Mode Preference</span>
                        <span className="font-semibold text-zinc-900 dark:text-zinc-50">{profile.work_mode}</span>
                      </div>
                      <div className="flex justify-between p-2.5 rounded-lg bg-zinc-50 dark:bg-zinc-900">
                        <span className="text-zinc-500">Expected Salary</span>
                        <span className="font-semibold text-zinc-900 dark:text-zinc-50">{profile.expected_salary || "Not Specified"}</span>
                      </div>
                      <div className="flex justify-between p-2.5 rounded-lg bg-zinc-50 dark:bg-zinc-900">
                        <span className="text-zinc-500">Max Applications / Day</span>
                        <span className="font-semibold text-zinc-900 dark:text-zinc-50">{profile.max_applications_per_day}</span>
                      </div>
                      <div className="flex justify-between p-2.5 rounded-lg bg-zinc-50 dark:bg-zinc-900">
                        <span className="text-zinc-500">Automation Search Status</span>
                        <span className={`font-semibold px-2 py-0.5 rounded-md text-xs inline-flex items-center ${
                          profile.job_search_status === "Active"
                            ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
                            : "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400"
                        }`}>
                          {profile.job_search_status}
                        </span>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Skills Card */}
                  <Card className="border border-zinc-200 dark:border-zinc-800 shadow-sm">
                    <CardHeader>
                      <CardTitle className="text-lg">Skills & Expertise</CardTitle>
                    </CardHeader>
                    <CardContent className="flex flex-wrap gap-2">
                      {profile.skills.map((skill, idx) => (
                        <span
                          key={idx}
                          className="px-3 py-1 rounded-full bg-indigo-50/50 dark:bg-indigo-950/20 text-indigo-700 dark:text-indigo-400 border border-indigo-100 dark:border-indigo-900/30 text-sm font-semibold"
                        >
                          {skill}
                        </span>
                      ))}
                      {profile.skills.length === 0 && (
                        <span className="text-sm text-zinc-400">No skills listed.</span>
                      )}
                    </CardContent>
                  </Card>

                  {/* Academic & Education */}
                  <Card className="border border-zinc-200 dark:border-zinc-800 shadow-sm">
                    <CardHeader>
                      <CardTitle className="text-lg">Education</CardTitle>
                    </CardHeader>
                    <CardContent className="flex items-start gap-4">
                      <div className="p-3 bg-zinc-100 dark:bg-zinc-900 rounded-lg">
                        <svg className="h-6 w-6 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path d="M12 14l9-5-9-5-9 5 9 5z" />
                          <path d="M12 14l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14z" />
                        </svg>
                      </div>
                      <div>
                        <h4 className="font-semibold text-zinc-900 dark:text-zinc-50">{profile.degree}</h4>
                        <p className="text-sm text-zinc-600 dark:text-zinc-400">{profile.college}</p>
                        <p className="text-xs text-zinc-400 mt-1 font-mono">Class of {profile.graduation_year}</p>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Projects Card */}
                  <Card className="border border-zinc-200 dark:border-zinc-800 shadow-sm">
                    <CardHeader>
                      <CardTitle className="text-lg">Projects</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {profile.projects.map((proj, idx) => (
                        <div
                          key={idx}
                          className="p-4 border border-zinc-100 dark:border-zinc-900 rounded-xl bg-zinc-50/20 dark:bg-zinc-900/10 space-y-1.5"
                        >
                          <h4 className="font-semibold text-zinc-900 dark:text-zinc-50">{proj.name}</h4>
                          {proj.technologies_used && (
                            <p className="text-xs text-indigo-650 dark:text-indigo-400 font-mono">
                              Tech: {proj.technologies_used}
                            </p>
                          )}
                          <p className="text-sm text-zinc-600 dark:text-zinc-400">{proj.description}</p>
                        </div>
                      ))}
                      {profile.projects.length === 0 && (
                        <span className="text-sm text-zinc-400 block py-2">No projects listed.</span>
                      )}
                    </CardContent>
                  </Card>

                  {/* Certifications Card */}
                  <Card className="border border-zinc-200 dark:border-zinc-800 shadow-sm">
                    <CardHeader>
                      <CardTitle className="text-lg">Certifications</CardTitle>
                    </CardHeader>
                    <CardContent className="divide-y divide-zinc-100 dark:divide-zinc-900 space-y-3">
                      {profile.certifications.map((c, idx) => (
                        <div key={idx} className="flex justify-between items-center pt-3 first:pt-0">
                          <div>
                            <h4 className="font-semibold text-zinc-900 dark:text-zinc-50">{c.name}</h4>
                            <p className="text-xs text-zinc-500 dark:text-zinc-400">
                              Issued by {c.issuing_organization}
                            </p>
                          </div>
                          <span className="text-xs font-mono text-zinc-400 bg-zinc-100 dark:bg-zinc-900 px-2 py-0.5 rounded">
                            {c.year}
                          </span>
                        </div>
                      ))}
                      {profile.certifications.length === 0 && (
                        <span className="text-sm text-zinc-400 block">No certifications listed.</span>
                      )}
                    </CardContent>
                  </Card>
                </div>
              </div>
            ) : activeTab === "candidate" ? (
              <div className="space-y-6">
                <Card className="border border-zinc-200 dark:border-zinc-800 shadow-sm">
                  <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <CardTitle className="text-lg">Candidate Profile</CardTitle>
                      <CardDescription>Parsed resume intelligence generated by n8n.</CardDescription>
                    </div>
                    <Button variant="outline" size="sm" onClick={loadCandidateProfile} isLoading={fetchingCandidateProfile}>
                      Refresh
                    </Button>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    {fetchingCandidateProfile ? (
                      <div className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">Loading candidate profile...</div>
                    ) : !candidateProfile ? (
                      <div className="rounded-lg border border-dashed border-zinc-300 p-8 text-center dark:border-zinc-800">
                        <h3 className="font-semibold text-zinc-900 dark:text-zinc-50">No parsed profile yet.</h3>
                        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
                          Upload a resume and let the Resume Intelligence workflow store parsed results.
                        </p>
                      </div>
                    ) : (
                      <>
                        <div className="rounded-lg bg-zinc-50 p-4 dark:bg-zinc-900">
                          <div className="text-xs font-semibold uppercase text-zinc-500 dark:text-zinc-400">Professional Summary</div>
                          <p className="mt-2 text-sm leading-6 text-zinc-700 dark:text-zinc-300">
                            {candidateProfile.summary || "No summary generated yet."}
                          </p>
                        </div>

                        <div className="grid gap-4 lg:grid-cols-2">
                          {[
                            ["Skills", candidateProfile.skills],
                            ["Projects", candidateProfile.projects],
                            ["Experience", candidateProfile.experience],
                            ["Education", candidateProfile.education],
                            ["Certifications", candidateProfile.certifications],
                          ].map(([title, values]) => {
                            const items = Array.isArray(values) ? values : [];
                            return (
                              <div key={title as string} className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
                                <h3 className="font-semibold text-zinc-900 dark:text-zinc-50">{title as string}</h3>
                                {items.length > 0 ? (
                                  <ul className="mt-3 space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
                                    {items.map((item, index) => (
                                      <li key={index} className="rounded-md bg-zinc-50 px-3 py-2 dark:bg-zinc-900">
                                        {candidateItemText(item)}
                                      </li>
                                    ))}
                                  </ul>
                                ) : (
                                  <p className="mt-3 text-sm text-zinc-400">No data parsed yet.</p>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </>
                    )}
                  </CardContent>
                </Card>
              </div>
            ) : (
              <div className="space-y-6">
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
                  {platformCards.map((platform) => (
                    <button
                      key={platform.source}
                      onClick={() => setJobSourceTab(platform.source)}
                      className={`rounded-lg border bg-white p-4 text-left shadow-sm transition-colors dark:bg-zinc-900 ${
                        jobSourceTab === platform.source
                          ? "border-indigo-500 ring-2 ring-indigo-100 dark:border-indigo-400 dark:ring-indigo-950"
                          : "border-zinc-200 hover:border-zinc-300 dark:border-zinc-800 dark:hover:border-zinc-700"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-zinc-100 text-xs font-bold text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
                          {platform.icon}
                        </span>
                        <span className="text-2xl font-bold text-zinc-950 dark:text-zinc-50">{platform.count}</span>
                      </div>
                      <div className="mt-3 text-xs font-semibold uppercase text-zinc-500 dark:text-zinc-400">{platform.label}</div>
                      <div className="mt-1 text-[11px] text-zinc-400">
                        {platform.last_refresh_at ? `Updated ${new Date(platform.last_refresh_at).toLocaleString()}` : "No refresh yet"}
                      </div>
                    </button>
                  ))}
                </div>

                {/* Search / Filter header */}
                <div className="space-y-4 rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
                  <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                    <Input
                      placeholder="Search by title, company, or location..."
                      value={jobSearchQuery}
                      onChange={(e) => setJobSearchQuery(e.target.value)}
                      className="xl:max-w-md"
                    />
                    <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
                      <select
                        value={jobDiscoverySource}
                        onChange={(e) => setJobDiscoverySource(e.target.value as JobDiscoverySource)}
                        className="h-10 rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-200"
                      >
                        <option value="All">All Platforms</option>
                        <option value="Naukri">Naukri</option>
                        <option value="LinkedIn">LinkedIn</option>
                        <option value="Foundit">Foundit</option>
                        <option value="Indeed">Indeed</option>
                        <option value="Wellfound">Wellfound</option>
                        <option value="Cutshort">Cutshort</option>
                        <option value="Hirist">Hirist</option>
                      </select>
                      <select
                        value={jobWorkModeFilter}
                        onChange={(e) => setJobWorkModeFilter(e.target.value as typeof jobWorkModeFilter)}
                        className="h-10 rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-200"
                      >
                        <option value="All">All Modes</option>
                        <option value="Remote">Remote</option>
                        <option value="Hybrid">Hybrid</option>
                        <option value="Onsite">Onsite</option>
                      </select>
                      <select
                        value={jobSortBy}
                        onChange={(e) => setJobSortBy(e.target.value as typeof jobSortBy)}
                        className="h-10 rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-200"
                      >
                        <option value="newest">Newest</option>
                        <option value="oldest">Oldest</option>
                        <option value="company">Company Name</option>
                        <option value="match_score">Match Score</option>
                      </select>
                      <select
                        value={jobsPerPage}
                        onChange={(e) => setJobsPerPage(Number(e.target.value))}
                        className="h-10 rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-200"
                      >
                        <option value={10}>10 per page</option>
                        <option value={20}>20 per page</option>
                        <option value={50}>50 per page</option>
                      </select>
                      <Button
                        onClick={handleDiscoverJobs}
                        size="sm"
                        isLoading={discoveringJobs}
                        disabled={isConnectedJobSource && isDailyLimitActive}
                      >
                        {isConnectedJobSource && isDailyLimitActive
                          ? `Available in ${formatCountdown(dailyLimitRemainingSeconds)}`
                          : `Fetch ${jobDiscoverySource} Jobs`}
                      </Button>
                      <Button onClick={loadJobs} variant="outline" size="sm" isLoading={fetchingJobs}>
                        Refresh Jobs
                      </Button>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {[
                      ["All", jobCounters.total],
                      ["Discovered", jobCounters.discovered],
                      ["Saved", jobCounters.saved],
                      ["Applied", jobCounters.applied],
                      ["Skipped", jobCounters.skipped],
                    ].map(([statusLabel, count]) => (
                      <button
                        key={statusLabel}
                        onClick={() => setJobStatusFilter(statusLabel as JobStatus | "All")}
                        className={`rounded-md border px-3 py-2 text-sm font-semibold transition-colors ${
                          jobStatusFilter === statusLabel
                            ? "border-indigo-600 bg-indigo-50 text-indigo-700 dark:border-indigo-500 dark:bg-indigo-950/30 dark:text-indigo-300"
                            : "border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300 dark:hover:bg-zinc-900"
                        }`}
                      >
                        {statusLabel} <span className="ml-1 text-xs opacity-70">{count}</span>
                      </button>
                    ))}
                  </div>

                  <div className="flex flex-wrap gap-2 border-t border-zinc-200 pt-3 dark:border-zinc-800">
                    {platformCards.map((platform) => (
                      <button
                        key={`tab-${platform.source}`}
                        onClick={() => setJobSourceTab(platform.source)}
                        className={`rounded-md border px-3 py-2 text-sm font-semibold transition-colors ${
                          jobSourceTab === platform.source
                            ? "border-indigo-600 bg-indigo-50 text-indigo-700 dark:border-indigo-500 dark:bg-indigo-950/30 dark:text-indigo-300"
                            : "border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300 dark:hover:bg-zinc-900"
                        }`}
                      >
                        {platform.label} <span className="ml-1 text-xs opacity-70">{platform.count}</span>
                      </button>
                    ))}
                  </div>

                  {selectedJobIds.length > 0 && (
                    <div className="flex flex-col gap-3 rounded-lg border border-indigo-100 bg-indigo-50 p-3 text-sm dark:border-indigo-900/40 dark:bg-indigo-950/20 sm:flex-row sm:items-center sm:justify-between">
                      <span className="font-semibold text-indigo-800 dark:text-indigo-300">
                        {selectedJobIds.length} selected
                      </span>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" disabled={bulkUpdating} onClick={() => handleBulkUpdateJobStatus("Saved")}>
                          Save Selected
                        </Button>
                        <Button size="sm" variant="secondary" disabled={bulkUpdating} onClick={() => handleBulkUpdateJobStatus("Skipped")}>
                          Skip Selected
                        </Button>
                      </div>
                    </div>
                  )}
                </div>

                {(jobsMessage || jobsError) && (
                  <div className={`rounded-lg border px-4 py-3 text-sm ${
                    jobsError
                      ? "border-red-200 bg-red-50 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400"
                      : "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-400"
                  }`}>
                    {jobsError || jobsMessage}
                  </div>
                )}

                {fetchingJobs && jobs.length === 0 ? (
                  <div className="grid gap-4 lg:grid-cols-2">
                    {[0, 1, 2, 3].map((item) => (
                      <Card key={item} className="rounded-lg">
                        <CardContent className="space-y-4 p-5">
                          <div className="h-4 w-2/3 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
                          <div className="h-3 w-1/3 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
                          <div className="grid grid-cols-3 gap-3">
                            <div className="h-3 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
                            <div className="h-3 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
                            <div className="h-3 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                ) : jobs.length === 0 ? (
                  <Card className="rounded-lg">
                    <CardContent className="flex flex-col items-center justify-center gap-4 p-10 text-center">
                      <div>
                        <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50">No jobs found yet.</h3>
                        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                          Fetch matching jobs from the selected website to start building your pipeline.
                        </p>
                      </div>
                      <Button
                        onClick={handleDiscoverJobs}
                        isLoading={discoveringJobs}
                        disabled={isConnectedJobSource && isDailyLimitActive}
                      >
                        {isConnectedJobSource && isDailyLimitActive
                          ? `Available in ${formatCountdown(dailyLimitRemainingSeconds)}`
                          : `Fetch ${jobDiscoverySource} Jobs`}
                      </Button>
                    </CardContent>
                  </Card>
                ) : filteredJobs.length === 0 ? (
                  <Card className="rounded-lg">
                    <CardContent className="p-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
                      No jobs match the current filters.
                    </CardContent>
                  </Card>
                ) : (
                  <>
                    <div className="flex items-center gap-3 text-sm text-zinc-500 dark:text-zinc-400">
                      <label className="inline-flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={allPageJobsSelected}
                          onChange={toggleSelectPageJobs}
                          className="h-4 w-4 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500"
                        />
                        Select page
                      </label>
                      <span>
                        Showing {(jobsPage - 1) * jobsPerPage + 1}-{Math.min(jobsPage * jobsPerPage, filteredJobs.length)} of {filteredJobs.length}
                      </span>
                    </div>

                    <div className="grid gap-4 lg:grid-cols-2">
                      {paginatedJobs.map((job) => {
                        const canOpenJob = isValidSupportedJobUrl(job.apply_url, job.source);
                        return (
                          <Card key={job.id} className="rounded-lg transition-shadow hover:shadow-md" onClick={() => setSelectedJob(job)}>
                            <CardContent className="space-y-4 p-5">
                              <div className="flex items-start gap-3">
                                <input
                                  type="checkbox"
                                  checked={selectedJobIds.includes(job.id)}
                                  onClick={(e) => e.stopPropagation()}
                                  onChange={() => toggleSelectedJob(job.id)}
                                  className="mt-1 h-4 w-4 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500"
                                />
                                <div className="min-w-0 flex-1">
                                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                                    <div>
                                      <h3 className="text-base font-bold text-zinc-950 dark:text-zinc-50">{job.title}</h3>
                                      <p className="mt-1 text-sm font-medium text-zinc-600 dark:text-zinc-300">{job.company}</p>
                                    </div>
                                    <span className={`w-fit rounded-md px-2.5 py-1 text-xs font-bold ${statusBadgeClass(job.status)}`}>
                                      {job.status}
                                    </span>
                                  </div>
                                </div>
                              </div>

                              <div className="grid gap-3 text-sm sm:grid-cols-2">
                                <div>
                                  <span className="block text-xs font-semibold uppercase text-zinc-400">Location</span>
                                  <span className="font-medium text-zinc-800 dark:text-zinc-200">{job.location || "N/A"}</span>
                                </div>
                                <div>
                                  <span className="block text-xs font-semibold uppercase text-zinc-400">Source</span>
                                  <span className="font-medium text-indigo-600 dark:text-indigo-400">{job.source || "Naukri"}</span>
                                </div>
                                <div>
                                  <span className="block text-xs font-semibold uppercase text-zinc-400">Date Found</span>
                                  <span className="font-medium text-zinc-800 dark:text-zinc-200">{new Date(job.created_at).toLocaleDateString()}</span>
                                </div>
                                <div>
                                  <span className="block text-xs font-semibold uppercase text-zinc-400">Match Score</span>
                                  <MatchScoreBadge score={job.match_score} />
                                </div>
                              </div>

                              <details
                                className="rounded-md border border-zinc-200 bg-zinc-50/60 p-3 dark:border-zinc-800 dark:bg-zinc-900/30"
                                onClick={(event) => event.stopPropagation()}
                              >
                                <summary className="cursor-pointer text-xs font-bold text-zinc-700 dark:text-zinc-200">
                                  Match details
                                </summary>
                                <div className="mt-3 grid gap-4 sm:grid-cols-3">
                                  <div>
                                    <p className="mb-2 text-xs font-bold text-emerald-700 dark:text-emerald-300">Matched Skills</p>
                                    <MatchList items={job.matched_skills || []} tone="matched" emptyText="No required skills detected." />
                                  </div>
                                  <div>
                                    <p className="mb-2 text-xs font-bold text-red-700 dark:text-red-300">Missing Skills</p>
                                    <MatchList items={job.missing_skills || []} tone="missing" emptyText="No missing skills detected." />
                                  </div>
                                  <div>
                                    <p className="mb-2 text-xs font-bold text-zinc-700 dark:text-zinc-200">Experience Gap</p>
                                    <p className="text-xs text-zinc-600 dark:text-zinc-300">
                                      {(job.experience_gap || 0) > 0
                                        ? `Needs ${job.experience_gap} more year${job.experience_gap === 1 ? "" : "s"}`
                                        : "Experience requirement met"}
                                    </p>
                                  </div>
                                </div>
                                {job.score_breakdown_json?.explanations?.semantic && (
                                  <div className="mt-3 border-t border-zinc-200 pt-3 dark:border-zinc-800">
                                    <p className="text-xs font-bold text-zinc-700 dark:text-zinc-200">Why this score?</p>
                                    <p className="mt-1 text-xs leading-5 text-zinc-600 dark:text-zinc-300">
                                      {job.score_breakdown_json.explanations.semantic}
                                    </p>
                                  </div>
                                )}
                              </details>

                              <div className="flex flex-wrap justify-end gap-2" onClick={(e) => e.stopPropagation()}>
                                {canOpenJob ? (
                                  <a
                                    href={job.apply_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="inline-flex h-8 items-center justify-center rounded-md px-3 text-xs font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-900"
                                  >
                                    View
                                  </a>
                                ) : (
                                  <Button variant="ghost" size="sm" disabled>
                                    View
                                  </Button>
                                )}
                                <Button variant="outline" size="sm" disabled={updatingJobId === job.id || job.status === "Saved"} onClick={() => handleUpdateJobStatus(job.id, "Saved")}>
                                  Save
                                </Button>
                                <Button variant="secondary" size="sm" disabled={updatingJobId === job.id || job.status === "Skipped"} onClick={() => handleUpdateJobStatus(job.id, "Skipped")}>
                                  Skip
                                </Button>
                                <Button size="sm" isLoading={tailoringJobId === job.id} onClick={() => handleTailorResume(job.id)}>
                                  Tailor Resume
                                </Button>
                              </div>

                              {tailoringJobId === job.id && (
                                <div className="rounded-md border border-indigo-100 bg-indigo-50 px-3 py-2 text-sm font-medium text-indigo-700 dark:border-indigo-900/40 dark:bg-indigo-950/20 dark:text-indigo-300">
                                  {tailoringStatusMessage || "Generating tailored resume..."}
                                </div>
                              )}

                              {tailoringResultJobId === job.id && tailoringResult && (
                                <div className="space-y-3 rounded-md border border-emerald-100 bg-emerald-50 px-3 py-3 dark:border-emerald-900/40 dark:bg-emerald-950/20">
                                  <p className="text-sm font-semibold text-emerald-700 dark:text-emerald-300">Resume generated successfully</p>
                                  <div className="flex flex-wrap gap-2">
                                    <Button size="sm" onClick={() => handleDownloadTailoredResume(tailoringResult.pdf_url || tailoringResult.download_url, tailoringResult.resume_id)}>
                                      Download Resume
                                    </Button>
                                    <Button variant="outline" size="sm" onClick={() => handlePreviewTailoredResume(tailoringResult.pdf_url || tailoringResult.preview_url)}>
                                      Preview Resume
                                    </Button>
                                    <Button variant="secondary" size="sm" onClick={() => handleTailorResume(job.id)}>
                                      Regenerate Resume
                                    </Button>
                                  </div>
                                </div>
                              )}
                            </CardContent>
                          </Card>
                        );
                      })}
                    </div>

                    <div className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-3 text-sm dark:border-zinc-800 dark:bg-zinc-950 sm:flex-row sm:items-center sm:justify-between">
                      <span className="text-zinc-500 dark:text-zinc-400">Page {jobsPage} of {totalJobPages}</span>
                      <div className="flex gap-2">
                        <Button variant="outline" size="sm" disabled={jobsPage <= 1} onClick={() => setJobsPage(page => Math.max(1, page - 1))}>
                          Previous
                        </Button>
                        <Button variant="outline" size="sm" disabled={jobsPage >= totalJobPages} onClick={() => setJobsPage(page => Math.min(totalJobPages, page + 1))}>
                          Next
                        </Button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        )}

      {/* JOB DETAIL MODAL */}
      {selectedJob && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-zinc-950/60 backdrop-blur-sm">
          <div className="bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 w-full max-w-2xl max-h-[85vh] rounded-xl overflow-hidden flex flex-col shadow-2xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/50">
              <div>
                <h2 className="text-xl font-bold text-zinc-900 dark:text-zinc-50">{selectedJob.title}</h2>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">{selectedJob.company} â€¢ {selectedJob.location || "Location Not Specified"}</p>
              </div>
              <button onClick={() => setSelectedJob(null)} className="text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 text-lg font-bold">
                âœ•
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 space-y-6 text-sm">
              <div className="grid grid-cols-2 gap-4 border border-zinc-150 dark:border-zinc-800 p-4 rounded-lg bg-zinc-50/50 dark:bg-zinc-900/20">
                <div>
                  <span className="text-zinc-400 font-semibold block text-xs">SOURCE</span>
                  <span className="font-medium text-zinc-900 dark:text-zinc-100">{selectedJob.source || "Naukri"}</span>
                </div>
                <div>
                  <span className="text-zinc-400 font-semibold block text-xs">DATE FOUND</span>
                  <span className="font-medium text-zinc-900 dark:text-zinc-100">{new Date(selectedJob.created_at).toLocaleString()}</span>
                </div>
                <div>
                  <span className="text-zinc-400 font-semibold block text-xs">CURRENT STATUS</span>
                  <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ${
                    selectedJob.status === "Discovered" ? "bg-blue-50 text-blue-700 dark:bg-blue-950/20 dark:text-blue-400" :
                    selectedJob.status === "Saved" ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/20 dark:text-indigo-400" :
                    selectedJob.status === "Applied" ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-400" :
                    selectedJob.status === "Skipped" ? "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300" :
                    "bg-amber-50 text-amber-700 dark:bg-amber-950/20 dark:text-amber-400"
                  }`}>{selectedJob.status}</span>
                </div>
                {selectedJob.match_score !== undefined && selectedJob.match_score !== null && (
                  <div>
                    <span className="text-zinc-400 font-semibold block text-xs">MATCH SCORE</span>
                    <MatchScoreBadge score={selectedJob.match_score} />
                  </div>
                )}
              </div>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-zinc-800 dark:text-zinc-200">Semantic Match Analysis</h3>
                  <span className="text-xs text-zinc-500">
                    {selectedJob.score_breakdown_json?.model || "Hugging Face embedding model"}
                  </span>
                </div>
                <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold">Profile and job embedding similarity</span>
                    <span className="text-lg font-bold">{Math.round(selectedJob.semantic_score ?? selectedJob.match_score ?? 0)}%</span>
                  </div>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
                    <div
                      className="h-full rounded-full bg-indigo-600"
                      style={{ width: `${Math.max(0, Math.min(100, selectedJob.semantic_score ?? selectedJob.match_score ?? 0))}%` }}
                    />
                  </div>
                </div>
                <div className="grid gap-4 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800 sm:grid-cols-2">
                  <div>
                    <h4 className="mb-2 text-xs font-bold text-emerald-700 dark:text-emerald-300">Matched Skills</h4>
                    <MatchList items={selectedJob.matched_skills || []} tone="matched" emptyText="No explicit required skills were detected." />
                  </div>
                  <div>
                    <h4 className="mb-2 text-xs font-bold text-red-700 dark:text-red-300">Missing Skills</h4>
                    <MatchList items={selectedJob.missing_skills || []} tone="missing" emptyText="No missing skills were detected." />
                  </div>
                  <div>
                    <h4 className="mb-2 text-xs font-bold text-emerald-700 dark:text-emerald-300">Matched Tools</h4>
                    <MatchList items={selectedJob.matched_tools || []} tone="matched" emptyText="No explicit tools were detected." />
                  </div>
                  <div>
                    <h4 className="mb-2 text-xs font-bold text-red-700 dark:text-red-300">Missing Tools</h4>
                    <MatchList items={selectedJob.missing_tools || []} tone="missing" emptyText="No missing tools were detected." />
                  </div>
                </div>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  {selectedJob.score_breakdown_json?.explanations?.semantic || "The score is generated from cosine similarity between candidate and job embeddings."}
                </p>
              </div>
              <div>
                <h3 className="font-bold text-zinc-805 dark:text-zinc-200 border-b pb-1 mb-2">Job Description</h3>
                <p className="text-zinc-650 dark:text-zinc-350 leading-relaxed whitespace-pre-line bg-zinc-50 dark:bg-zinc-900/10 p-4 rounded-lg border dark:border-zinc-800/60 font-serif">
                  {selectedJob.description || "No job description provided by platform."}
                </p>
              </div>
              {isValidSupportedJobUrl(selectedJob.apply_url, selectedJob.source) && (
                <div>
                  <h3 className="font-bold text-zinc-800 dark:text-zinc-200 mb-2">Application Link</h3>
                  <a
                    href={selectedJob.apply_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-indigo-600 dark:text-indigo-400 font-semibold hover:underline bg-indigo-50 dark:bg-indigo-950/20 px-4 py-2.5 rounded-lg border border-indigo-100 dark:border-indigo-900/30"
                  >
                    Apply Directly on Platform
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                </div>
              )}
            </div>
            <div className="px-6 py-4 border-t border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/50 flex flex-wrap gap-2 justify-between items-center">
              <div className="flex gap-2">
                <select
                  value={selectedJob.status}
                  onChange={(e) => {
                    const nextStatus = e.target.value as JobStatus;
                    handleUpdateJobStatus(selectedJob.id, nextStatus);
                    setSelectedJob({ ...selectedJob, status: nextStatus });
                  }}
                  className="px-2 py-1 bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded text-sm focus:outline-none text-zinc-850 dark:text-zinc-200"
                >
                  <option value="Discovered">Discovered</option>
                  <option value="Saved">Saved</option>
                  <option value="Skipped">Skipped</option>
                </select>
                <span className="text-xs text-zinc-400 self-center">Update status</span>
              </div>
              <div className="flex flex-col items-end gap-2">
                {tailoringJobId === selectedJob.id && (
                  <span className="text-sm font-medium text-indigo-600 dark:text-indigo-300">
                    {tailoringStatusMessage || "Generating tailored resume..."}
                  </span>
                )}
                {tailoringResultJobId === selectedJob.id && tailoringResult && (
                  <div className="flex flex-wrap justify-end gap-2">
                    <span className="w-full text-right text-sm font-semibold text-emerald-600 dark:text-emerald-300">Resume generated successfully</span>
                    <Button size="sm" onClick={() => handleDownloadTailoredResume(tailoringResult.pdf_url || tailoringResult.download_url, tailoringResult.resume_id)}>
                      Download Resume
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => handlePreviewTailoredResume(tailoringResult.pdf_url || tailoringResult.preview_url)}>
                      Preview Resume
                    </Button>
                    <Button variant="secondary" size="sm" onClick={() => handleTailorResume(selectedJob.id)}>
                      Regenerate Resume
                    </Button>
                  </div>
                )}
                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => router.push(`/jobs/${selectedJob.id}`)}>
                    Full Match Analysis
                  </Button>
                  <Button variant="outline" isLoading={tailoringJobId === selectedJob.id} onClick={() => handleTailorResume(selectedJob.id)}>
                    Tailor Resume
                  </Button>
                  <Button onClick={() => setSelectedJob(null)}>Close</Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
      </main>

      {/* Footer */}
      <footer className="bg-white dark:bg-zinc-950 border-t border-zinc-200 dark:border-zinc-900 mt-auto">
        <div className="mx-auto max-w-7xl px-6 py-6 flex items-center justify-between text-xs text-zinc-500 dark:text-zinc-400">
          <span>AI Career Copilot Dashboard</span>
          <span>Version 1.0.0 (MVP)</span>
        </div>
      </footer>
    </div>
  );
}

