"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { fetchAdminUsers, deleteUser, toggleAdminStatus, fetchUserDetails, fetchAdminMonitoringSummary } from "@/services/auth";
import { fetchAdminJobs, isValidSupportedJobUrl, JOB_SOURCES, updateJobStatus, JobStatus } from "@/services/jobs";
import { User } from "@/types/auth";

export default function AdminPage() {
  const { user, isAuthenticated, isLoading, logout } = useAuth();
  const router = useRouter();
  
  const [users, setUsers] = useState<any[]>([]);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState("");
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [monitoringSummary, setMonitoringSummary] = useState<any | null>(null);

  // Search Filters
  const [searchRole, setSearchRole] = useState("");
  const [searchSkills, setSearchSkills] = useState("");

  // Modal / Detail Pane State
  const [selectedUser, setSelectedUser] = useState<any | null>(null);
  const [loadingDetails, setLoadingDetails] = useState(false);

  // Admin Jobs UI State
  const [activeTab, setActiveTab] = useState<"users" | "jobs">("users");
  const [jobs, setJobs] = useState<any[]>([]);
  const [fetchingJobs, setFetchingJobs] = useState(false);
  const [selectedJob, setSelectedJob] = useState<any | null>(null);
  const [jobSearchCompany, setJobSearchCompany] = useState("");
  const [jobSearchTitle, setJobSearchTitle] = useState("");
  const [jobSourceFilter, setJobSourceFilter] = useState("All");
  const [jobStatusFilter, setJobStatusFilter] = useState("All");

  const loadJobs = async (company = "", title = "", source = "All", status = "All") => {
    setFetchingJobs(true);
    setError("");
    try {
      const filters: any = {};
      if (company) filters.company = company;
      if (title) filters.title = title;
      if (source !== "All") filters.source = source;
      if (status !== "All") filters.status = status;
      
      const data = await fetchAdminJobs(filters);
      setJobs(data);
    } catch (err: any) {
      setError(err.message || "Failed to load jobs database");
    } finally {
      setFetchingJobs(false);
    }
  };

  const loadMonitoringSummary = async () => {
    try {
      const data = await fetchAdminMonitoringSummary();
      setMonitoringSummary(data);
    } catch (err) {
      console.error("Failed to load admin monitoring summary:", err);
    }
  };

  const handleUpdateJobStatus = async (jobId: number, newStatus: JobStatus) => {
    setError("");
    try {
      await updateJobStatus(jobId, newStatus);
      
      // Update local state
      setJobs(prevJobs =>
        prevJobs.map(j => (j.id === jobId ? { ...j, status: newStatus } : j))
      );
      
      // Update selectedJob if open
      if (selectedJob && selectedJob.id === jobId) {
        setSelectedJob((prev: any) => prev ? { ...prev, status: newStatus } : null);
      }
    } catch (err: any) {
      setError(err.message || "Failed to update job status");
    }
  };

  // Authorization gate: redirect if not admin
  useEffect(() => {
    if (!isLoading) {
      if (!isAuthenticated) {
        router.push("/login");
      } else if (!user?.is_admin) {
        router.push("/dashboard");
      }
    }
  }, [isLoading, isAuthenticated, user, router]);

  const loadUsers = async (role = "", skills = "") => {
    setFetching(true);
    setError("");
    try {
      const data = await fetchAdminUsers(role, skills);
      setUsers(data);
    } catch (err: any) {
      setError(err.message || "Failed to load registered users");
    } finally {
      setFetching(false);
    }
  };

  // Load user records on mount
  useEffect(() => {
    if (isAuthenticated && user?.is_admin) {
      loadUsers();
      loadJobs();
      loadMonitoringSummary();
    }
  }, [isAuthenticated, user]);

  const handleJobSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadJobs(jobSearchCompany, jobSearchTitle, jobSourceFilter, jobStatusFilter);
  };

  const handleJobClearSearch = () => {
    setJobSearchCompany("");
    setJobSearchTitle("");
    setJobSourceFilter("All");
    setJobStatusFilter("All");
    loadJobs("", "", "All", "All");
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadUsers(searchRole, searchSkills);
  };

  const handleClearSearch = () => {
    setSearchRole("");
    setSearchSkills("");
    loadUsers("", "");
  };

  const handleToggleAdmin = async (targetUserId: number, e?: React.MouseEvent) => {
    if (e) e.stopPropagation(); // prevent modal from opening when clicking action buttons
    
    setActionLoading(targetUserId);
    setError("");
    try {
      const updatedUser = await toggleAdminStatus(targetUserId);
      setUsers(users.map(u => u.id === targetUserId ? { ...u, is_admin: updatedUser.is_admin } : u));
      
      // Update selectedUser if open in modal
      if (selectedUser && selectedUser.id === targetUserId) {
        setSelectedUser((prev: any) => prev ? { ...prev, is_admin: updatedUser.is_admin } : null);
      }
    } catch (err: any) {
      setError(err.message || "Failed to toggle administrator role");
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeleteUser = async (targetUserId: number, e?: React.MouseEvent) => {
    if (e) e.stopPropagation(); // prevent modal from opening
    
    if (!window.confirm("Are you sure you want to permanently delete this user account? This action cannot be undone.")) {
      return;
    }
    
    setActionLoading(targetUserId);
    setError("");
    try {
      await deleteUser(targetUserId);
      setUsers(users.filter(u => u.id !== targetUserId));
      
      // Close modal if deleted user is selected
      if (selectedUser && selectedUser.id === targetUserId) {
        setSelectedUser(null);
      }
    } catch (err: any) {
      setError(err.message || "Failed to delete user account");
    } finally {
      setActionLoading(null);
    }
  };

  const handleUserClick = async (clickedUser: any) => {
    setSelectedUser(clickedUser);
    setLoadingDetails(true);
    try {
      // Fetch fresh details from the dedicated backend endpoint
      const freshDetails = await fetchUserDetails(clickedUser.id);
      setSelectedUser(freshDetails);
    } catch (err) {
      console.error("Could not fetch user fresh details:", err);
      // Fallback to existing list details if endpoint fails
    } finally {
      setLoadingDetails(false);
    }
  };

  // Format File Size
  const formatBytes = (bytes: number, decimals = 2) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
  };

  // While checking auth states, show loader
  if (isLoading || !isAuthenticated || !user?.is_admin) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-950">
        <div className="flex flex-col items-center gap-4">
          <svg className="animate-spin h-10 w-10 text-indigo-600" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <span className="text-sm font-medium text-zinc-600">Verifying administrator credentials...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950 flex flex-col transition-colors duration-200">
      {/* Top Navigation */}
      <header className="sticky top-0 z-40 w-full border-b border-zinc-200 bg-white/85 backdrop-blur-md dark:border-zinc-800 dark:bg-zinc-950/85">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <div className="flex items-center gap-2">
            <svg className="h-8 w-8 text-indigo-600 dark:text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <span className="text-xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
              AI Career Copilot
            </span>
            <span className="ml-2 rounded-full bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400 px-2.5 py-0.5 text-xs font-semibold">
              Admin Portal
            </span>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/dashboard">
              <Button variant="outline" size="sm">
                Dashboard Overview
              </Button>
            </Link>
            <Button variant="ghost" size="sm" onClick={logout}>
              Sign Out
            </Button>
          </div>
        </div>
      </header>

      {/* Main Admin Section */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
              {activeTab === "users" ? "User Account Management" : "Discovered Jobs Database"}
            </h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
              {activeTab === "users"
                ? "Monitor registered users, inspect resume documents, profile setups, and manage user permissions."
                : "Monitor and manage all jobs discovered by scrape nodes across all registered user accounts."}
            </p>
          </div>
          {/* Tab Selector */}
          <div className="flex border border-zinc-200 dark:border-zinc-800 rounded-lg overflow-hidden bg-white dark:bg-zinc-950 p-1">
            <button
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                activeTab === "users"
                  ? "bg-indigo-650 text-white dark:bg-indigo-500"
                  : "text-zinc-500 dark:text-zinc-400 hover:text-zinc-800"
              }`}
              onClick={() => setActiveTab("users")}
            >
              User Accounts
            </button>
            <button
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                activeTab === "jobs"
                  ? "bg-indigo-600 text-white dark:bg-indigo-500"
                  : "text-zinc-500 dark:text-zinc-400 hover:text-zinc-800"
              }`}
              onClick={() => {
                setActiveTab("jobs");
                loadJobs();
              }}
            >
              Jobs Database
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-md bg-red-50 p-4 text-sm text-red-650 dark:bg-red-950/20 dark:text-red-400 border border-red-200 dark:border-red-900/40">
            {error}
          </div>
        )}

        {activeTab === "users" ? (
          <>
            {/* Info stats row */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Card>
                <CardHeader className="pb-2">
                  <span className="text-sm font-medium text-zinc-500">Students Signed In</span>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">{monitoringSummary ? monitoringSummary.total_students : "..."}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <span className="text-sm font-medium text-zinc-500">Students at Daily Limit</span>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">
                    {monitoringSummary ? monitoringSummary.students_at_daily_limit : "..."}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <span className="text-sm font-medium text-zinc-500">Jobs Found Today</span>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">
                    {monitoringSummary ? monitoringSummary.jobs_discovered_last_24h : "..."}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <span className="text-sm font-medium text-zinc-500">Profiles Completed</span>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">
                    {monitoringSummary ? monitoringSummary.profiles_completed : "..."}
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Search Filter Header */}
            <Card className="border border-zinc-200 dark:border-zinc-800">
              <CardContent className="p-4 md:p-6">
                <form onSubmit={handleSearchSubmit} className="flex flex-col md:flex-row items-end gap-4">
                  <div className="flex-1 w-full space-y-1">
                    <Label htmlFor="search_role">Filter by Desired Role</Label>
                    <Input
                      id="search_role"
                      value={searchRole}
                      onChange={e => setSearchRole(e.target.value)}
                      placeholder="e.g. Frontend, Data Scientist, Tech Lead"
                    />
                  </div>
                  <div className="flex-1 w-full space-y-1">
                    <Label htmlFor="search_skills">Filter by Skill Tag</Label>
                    <Input
                      id="search_skills"
                      value={searchSkills}
                      onChange={e => setSearchSkills(e.target.value)}
                      placeholder="e.g. Python, React, AWS"
                    />
                  </div>
                  <div className="flex gap-2 w-full md:w-auto">
                    <Button type="submit" className="flex-1 md:flex-initial">
                      Search
                    </Button>
                    {(searchRole || searchSkills) && (
                      <Button type="button" variant="outline" onClick={handleClearSearch} className="flex-1 md:flex-initial">
                        Clear
                      </Button>
                    )}
                  </div>
                </form>
              </CardContent>
            </Card>

            {/* User Database Table */}
            <Card className="overflow-hidden border border-zinc-200 dark:border-zinc-800">
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left text-sm text-zinc-500 dark:text-zinc-400">
                  <thead className="bg-zinc-50 text-xs uppercase text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 border-b border-zinc-200 dark:border-zinc-800">
                    <tr>
                      <th scope="col" className="px-6 py-4 font-semibold">#</th>
                      <th scope="col" className="px-6 py-4 font-semibold">Full Name / Account</th>
                      <th scope="col" className="px-6 py-4 font-semibold">Desired Role</th>
                      <th scope="col" className="px-6 py-4 font-semibold">Resume Status</th>
                      <th scope="col" className="px-6 py-4 font-semibold">Role</th>
                      <th scope="col" className="px-6 py-4 font-semibold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800 bg-white dark:bg-zinc-950">
                    {fetching ? (
                      <tr>
                        <td colSpan={6} className="px-6 py-10 text-center text-zinc-400">
                          Loading registered users list...
                        </td>
                      </tr>
                    ) : users.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="px-6 py-10 text-center text-zinc-400">
                          No registered users found matching the filter criteria.
                        </td>
                      </tr>
                    ) : (
                      users.map((row, index) => {
                        const isSelf = row.email === user?.email;
                        
                        return (
                          <tr
                            key={row.id}
                            className="hover:bg-zinc-50/80 dark:hover:bg-zinc-900/40 cursor-pointer transition-colors"
                            onClick={() => handleUserClick(row)}
                          >
                            <td className="px-6 py-4 font-mono font-medium text-zinc-900 dark:text-zinc-100">
                              #{index + 1}
                            </td>
                            <td className="px-6 py-4">
                              <div className="font-semibold text-zinc-900 dark:text-zinc-100">
                                {row.profile?.full_name || row.name || "Setup Incomplete"}
                                {isSelf && <span className="ml-2 text-xs font-normal text-zinc-450">(You)</span>}
                              </div>
                              <div className="text-xs text-zinc-400">{row.email}</div>
                            </td>
                            <td className="px-6 py-4 font-medium text-zinc-800 dark:text-zinc-200">
                              {row.profile?.desired_role || <span className="text-zinc-400 italic">No Profile Setup</span>}
                            </td>
                            <td className="px-6 py-4">
                              {row.resume ? (
                                <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-semibold text-xs">
                                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                                  </svg>
                                  Uploaded
                                </span>
                              ) : (
                                <span className="text-zinc-400 text-xs">Not Uploaded</span>
                              )}
                            </td>
                            <td className="px-6 py-4">
                              <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ${
                                row.is_admin 
                                  ? "bg-red-50 text-red-700 ring-1 ring-inset ring-red-600/10 dark:bg-red-950/40 dark:text-red-400" 
                                  : "bg-zinc-100 text-zinc-700 ring-1 ring-inset ring-zinc-500/10 dark:bg-zinc-800 dark:text-zinc-300"
                              }`}>
                                {row.is_admin ? "Admin" : "User"}
                              </span>
                            </td>
                            <td className="px-6 py-4 text-right space-x-1.5" onClick={e => e.stopPropagation()}>
                              <Button
                                variant="ghost"
                                size="sm"
                                disabled={isSelf || actionLoading !== null}
                                onClick={(e) => handleToggleAdmin(row.id, e)}
                              >
                                {actionLoading === row.id ? "Updating..." : "Toggle Role"}
                              </Button>
                              <Button
                                variant="secondary"
                                size="sm"
                                className="text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                                disabled={isSelf || actionLoading !== null}
                                onClick={(e) => handleDeleteUser(row.id, e)}
                              >
                                {actionLoading === row.id ? "Deleting..." : "Delete"}
                              </Button>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </>
        ) : (
          <>
            {/* Jobs info stats row */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Card>
                <CardHeader className="pb-2">
                  <span className="text-sm font-medium text-zinc-500">Total Jobs Discovered</span>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">{fetchingJobs ? "..." : jobs.length}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <span className="text-sm font-medium text-zinc-500">Skipped Jobs</span>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">
                    {fetchingJobs ? "..." : jobs.filter(j => j.status === "Skipped").length}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <span className="text-sm font-medium text-zinc-500">Saved Jobs</span>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">
                    {fetchingJobs ? "..." : jobs.filter(j => j.status === "Saved").length}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <span className="text-sm font-medium text-zinc-500">Applied Jobs</span>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">
                    {fetchingJobs ? "..." : jobs.filter(j => j.status === "Applied").length}
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Jobs Search Filter Header */}
            <Card className="border border-zinc-200 dark:border-zinc-800">
              <CardContent className="p-4 md:p-6">
                <form onSubmit={handleJobSearchSubmit} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5 items-end">
                  <div className="space-y-1">
                    <Label htmlFor="search_title">Filter by Job Title</Label>
                    <Input
                      id="search_title"
                      value={jobSearchTitle}
                      onChange={e => setJobSearchTitle(e.target.value)}
                      placeholder="e.g. AI Engineer"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="search_company">Filter by Company</Label>
                    <Input
                      id="search_company"
                      value={jobSearchCompany}
                      onChange={e => setJobSearchCompany(e.target.value)}
                      placeholder="e.g. ABC Technologies"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="search_source">Filter by Source</Label>
                    <select
                      id="search_source"
                      value={jobSourceFilter}
                      onChange={e => setJobSourceFilter(e.target.value)}
                      className="w-full h-10 px-3 py-2 text-sm bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-md text-zinc-805 dark:text-zinc-200 focus:outline-none"
                    >
                      <option value="All">All Sources</option>
                      {JOB_SOURCES.map((source) => (
                        <option key={source} value={source}>{source}</option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="search_status">Filter by Status</Label>
                    <select
                      id="search_status"
                      value={jobStatusFilter}
                      onChange={e => setJobStatusFilter(e.target.value)}
                      className="w-full h-10 px-3 py-2 text-sm bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-md text-zinc-805 dark:text-zinc-200 focus:outline-none"
                    >
                      <option value="All">All Statuses</option>
                      <option value="Discovered">Discovered</option>
                      <option value="Saved">Saved</option>
                      <option value="Applied">Applied</option>
                      <option value="Skipped">Skipped</option>
                    </select>
                  </div>
                  <div className="flex gap-2 w-full">
                    <Button type="submit" className="flex-1">
                      Search
                    </Button>
                    {(jobSearchTitle || jobSearchCompany || jobSourceFilter !== "All" || jobStatusFilter !== "All") && (
                      <Button type="button" variant="outline" onClick={handleJobClearSearch} className="flex-1">
                        Clear
                      </Button>
                    )}
                  </div>
                </form>
              </CardContent>
            </Card>

            {/* Jobs Database Table */}
            <Card className="overflow-hidden border border-zinc-200 dark:border-zinc-800">
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left text-sm text-zinc-500 dark:text-zinc-400">
                  <thead className="bg-zinc-50 text-xs uppercase text-zinc-750 dark:bg-zinc-900 dark:text-zinc-300 border-b border-zinc-200 dark:border-zinc-800 font-semibold">
                    <tr>
                      <th scope="col" className="px-6 py-4">#</th>
                      <th scope="col" className="px-6 py-4">Owner User</th>
                      <th scope="col" className="px-6 py-4">Job Info</th>
                      <th scope="col" className="px-6 py-4">Platform Source</th>
                      <th scope="col" className="px-6 py-4">Status</th>
                      <th scope="col" className="px-6 py-4">Date Discovered</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800 bg-white dark:bg-zinc-950">
                    {fetchingJobs ? (
                      <tr>
                        <td colSpan={6} className="px-6 py-10 text-center text-zinc-450">
                          Loading jobs list...
                        </td>
                      </tr>
                    ) : jobs.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="px-6 py-10 text-center text-zinc-450">
                          No discovered jobs found matching the filter criteria.
                        </td>
                      </tr>
                    ) : (
                      jobs.map((row, index) => {
                        return (
                          <tr
                            key={row.id}
                            className="hover:bg-zinc-50/80 dark:hover:bg-zinc-900/40 cursor-pointer transition-colors"
                            onClick={() => setSelectedJob(row)}
                          >
                            <td className="px-6 py-4 font-mono font-medium text-zinc-900 dark:text-zinc-100">
                              #{index + 1}
                            </td>
                            <td className="px-6 py-4">
                              <div className="font-semibold text-zinc-905 dark:text-zinc-100">
                                {row.user_name || "Unknown"}
                              </div>
                              <div className="text-xs text-zinc-400">{row.user_email}</div>
                            </td>
                            <td className="px-6 py-4">
                              <div className="font-semibold text-zinc-905 dark:text-zinc-100">
                                {row.title}
                              </div>
                              <div className="text-xs text-zinc-400">{row.company}</div>
                            </td>
                            <td className="px-6 py-4 font-medium text-zinc-800 dark:text-zinc-200">
                              <span className="text-indigo-650 dark:text-indigo-400 text-xs font-mono">{row.source || "Naukri"}</span>
                            </td>
                            <td className="px-6 py-4">
                              <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ${
                                row.status === "Discovered" ? "bg-blue-50 text-blue-700 dark:bg-blue-950/20 dark:text-blue-400" :
                                row.status === "Saved" ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/20 dark:text-indigo-400" :
                                row.status === "Applied" ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-400" :
                                row.status === "Skipped" ? "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300" :
                                "bg-amber-50 text-amber-700 dark:bg-amber-950/20 dark:text-amber-400"
                              }`}>
                                {row.status}
                              </span>
                            </td>
                            <td className="px-6 py-4 text-xs font-mono text-zinc-400">
                              {new Date(row.created_at).toLocaleDateString()}
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </>
        )}
      </main>

      {/* USER DETAIL MODAL POPUP */}
      {selectedUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-zinc-950/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 w-full max-w-4xl max-h-[85vh] rounded-xl overflow-hidden flex flex-col shadow-2xl animate-scale-up">
            
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/50">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <h2 className="text-xl font-bold text-zinc-900 dark:text-zinc-50">
                    User Footprint Detail
                  </h2>
                  <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ${
                    selectedUser.is_admin
                      ? "bg-red-50 text-red-700 ring-1 ring-inset ring-red-600/10 dark:bg-red-950/40 dark:text-red-400"
                      : "bg-zinc-100 text-zinc-700 ring-1 ring-inset ring-zinc-500/10 dark:bg-zinc-800 dark:text-zinc-300"
                  }`}>
                    {selectedUser.is_admin ? "Admin" : "User"}
                  </span>
                  {loadingDetails && (
                    <svg className="animate-spin h-4 w-4 text-indigo-600" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                  )}
                </div>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  Account ID: #{selectedUser.id} • Registered Name: {selectedUser.name || "Not Setup"}
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelectedUser(null)}
                className="h-8 w-8 p-0 rounded-full text-zinc-500 hover:text-zinc-800"
              >
                ✕
              </Button>
            </div>

            {/* Modal Body (Scrollable) */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {!selectedUser.profile ? (
                /* No Profile Case */
                <div className="text-center py-12 space-y-2 border border-dashed rounded-lg border-zinc-200 dark:border-zinc-800">
                  <p className="text-sm font-semibold text-zinc-500">
                    No Career Copilot profile setup completed for this account.
                  </p>
                  <p className="text-xs text-zinc-400">
                    The user has registered an account but has not yet completed the dashboard profile setup form.
                  </p>
                </div>
              ) : (
                /* Profile Setup Details */
                <div className="space-y-6">
                  {/* Row 1: Contact Details */}
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="p-4 border border-zinc-200 dark:border-zinc-800 rounded-lg">
                      <h3 className="font-bold text-zinc-900 dark:text-zinc-50 text-sm mb-2 border-b pb-1">
                        Contact Details
                      </h3>
                      <div className="space-y-1.5 text-sm">
                        <p><span className="text-zinc-400">Full Name:</span> {selectedUser.profile.full_name}</p>
                        <p><span className="text-zinc-400">Email:</span> {selectedUser.profile.email}</p>
                        <p><span className="text-zinc-400">Phone:</span> {selectedUser.profile.phone}</p>
                        <p><span className="text-zinc-400">Location:</span> {selectedUser.profile.location}</p>
                      </div>
                    </div>

                    <div className="p-4 border border-zinc-200 dark:border-zinc-800 rounded-lg">
                      <h3 className="font-bold text-zinc-900 dark:text-zinc-50 text-sm mb-2 border-b pb-1">
                        Professional Scope
                      </h3>
                      <div className="space-y-1.5 text-sm">
                        <p><span className="text-zinc-400">Desired Job Role:</span> {selectedUser.profile.desired_role}</p>
                        <p><span className="text-zinc-400">Years Experience:</span> {selectedUser.profile.years_experience}</p>
                        <p><span className="text-zinc-400">Current Designation:</span> {selectedUser.profile.current_designation || "N/A"}</p>
                        <p><span className="text-zinc-400">Current Company:</span> {selectedUser.profile.current_company || "N/A"}</p>
                      </div>
                    </div>
                  </div>

                  {/* Career goals & target preferences */}
                  <div className="p-4 border border-zinc-200 dark:border-zinc-800 rounded-lg">
                    <h3 className="font-bold text-zinc-900 dark:text-zinc-50 text-sm mb-2 border-b pb-1">
                      Job Preferences & Career Goals
                    </h3>
                    <div className="grid gap-4 sm:grid-cols-3 text-sm">
                      <div><span className="text-zinc-400">Target Title:</span> {selectedUser.profile.desired_job_title}</div>
                      <div><span className="text-zinc-400">Preferred Location:</span> {selectedUser.profile.preferred_location}</div>
                      <div><span className="text-zinc-400">Salary Expectation:</span> {selectedUser.profile.expected_salary || "Not specified"}</div>
                      <div><span className="text-zinc-400">Work Mode:</span> {selectedUser.profile.work_mode}</div>
                      <div><span className="text-zinc-400">Max Apps/Day:</span> {selectedUser.profile.max_applications_per_day}</div>
                      <div>
                        <span className="text-zinc-400">Automation Status:</span>{" "}
                        <span className={`font-semibold px-1.5 py-0.5 rounded text-xs ${
                          selectedUser.profile.job_search_status === "Active"
                            ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400"
                            : "bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400"
                        }`}>
                          {selectedUser.profile.job_search_status}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Skills tags */}
                  <div>
                    <h3 className="font-bold text-zinc-800 dark:text-zinc-200 text-sm mb-2">
                      Skills
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedUser.profile.skills?.map((skill: string, idx: number) => (
                        <span
                          key={idx}
                          className="px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-950/30 text-indigo-700 dark:text-indigo-400 text-xs font-semibold border border-indigo-100 dark:border-indigo-900/20"
                        >
                          {skill}
                        </span>
                      ))}
                      {(!selectedUser.profile.skills || selectedUser.profile.skills.length === 0) && (
                        <span className="text-xs text-zinc-400 italic">No skills listed.</span>
                      )}
                    </div>
                  </div>

                  {/* Education details */}
                  <div className="p-4 border border-zinc-200 dark:border-zinc-800 rounded-lg">
                    <h3 className="font-bold text-zinc-900 dark:text-zinc-50 text-sm mb-2 border-b pb-1">
                      Academic History
                    </h3>
                    <div className="text-sm">
                      <p className="font-semibold text-zinc-800 dark:text-zinc-200">{selectedUser.profile.degree}</p>
                      <p className="text-zinc-500 dark:text-zinc-400">{selectedUser.profile.college}</p>
                      <p className="text-xs text-zinc-400 mt-1">Class of {selectedUser.profile.graduation_year}</p>
                    </div>
                  </div>

                  {/* Dynamic Projects section */}
                  <div>
                    <h3 className="font-bold text-zinc-800 dark:text-zinc-200 text-sm mb-2">
                      Personal Projects
                    </h3>
                    <div className="space-y-3">
                      {selectedUser.profile.projects?.map((proj: any, idx: number) => (
                        <div
                          key={idx}
                          className="p-3 border border-zinc-100 dark:border-zinc-900 rounded-lg bg-zinc-50/50 dark:bg-zinc-900/10 space-y-1"
                        >
                          <h4 className="font-semibold text-sm text-zinc-900 dark:text-zinc-50">{proj.name}</h4>
                          <p className="text-xs text-indigo-650 dark:text-indigo-400 font-mono">Tech: {proj.technologies_used}</p>
                          <p className="text-xs text-zinc-600 dark:text-zinc-400">{proj.description}</p>
                        </div>
                      ))}
                      {(!selectedUser.profile.projects || selectedUser.profile.projects.length === 0) && (
                        <span className="text-xs text-zinc-400 italic">No projects listed.</span>
                      )}
                    </div>
                  </div>

                  {/* Dynamic Certifications section */}
                  <div>
                    <h3 className="font-bold text-zinc-800 dark:text-zinc-200 text-sm mb-2">
                      Certifications
                    </h3>
                    <div className="space-y-2">
                      {selectedUser.profile.certifications?.map((c: any, idx: number) => (
                        <div
                          key={idx}
                          className="flex justify-between items-center p-3 border border-zinc-100 dark:border-zinc-900 rounded-lg"
                        >
                          <div>
                            <h4 className="font-semibold text-xs text-zinc-900 dark:text-zinc-50">{c.name}</h4>
                            <p className="text-[11px] text-zinc-500">Issued by {c.issuing_organization}</p>
                          </div>
                          <span className="text-xs font-mono bg-zinc-100 dark:bg-zinc-900 px-2 py-0.5 rounded text-zinc-400">
                            {c.year}
                          </span>
                        </div>
                      ))}
                      {(!selectedUser.profile.certifications || selectedUser.profile.certifications.length === 0) && (
                        <span className="text-xs text-zinc-400 italic">No certifications listed.</span>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Resume Info */}
              <div className="p-4 border border-zinc-200 dark:border-zinc-800 rounded-lg bg-indigo-50/10 dark:bg-indigo-950/5">
                <h3 className="font-bold text-zinc-900 dark:text-zinc-50 text-sm mb-2 border-b pb-1">
                  Resume File Metadata
                </h3>
                {selectedUser.resume ? (
                  <div className="flex items-center gap-3 text-sm">
                    <svg className="h-8 w-8 text-indigo-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <div>
                      <p className="font-semibold text-zinc-800 dark:text-zinc-200">
                        {selectedUser.resume.file_name}
                      </p>
                      <p className="text-xs text-zinc-400">
                        Size: {formatBytes(selectedUser.resume.file_size)} • Format: {selectedUser.resume.file_type.split("/")[1]?.toUpperCase()}
                      </p>
                      <p className="text-[11px] text-zinc-400">
                        Uploaded: {new Date(selectedUser.resume.uploaded_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-zinc-400 italic">
                    No resume document uploaded by this user.
                  </p>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/50 flex flex-col sm:flex-row sm:justify-between items-center gap-3">
              <div>
                {selectedUser.email !== user?.email && (
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={actionLoading !== null}
                      onClick={() => handleToggleAdmin(selectedUser.id)}
                    >
                      {actionLoading === selectedUser.id ? "Updating..." : "Toggle Admin Status"}
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      className="text-red-650 hover:text-red-700"
                      disabled={actionLoading !== null}
                      onClick={() => handleDeleteUser(selectedUser.id)}
                    >
                      {actionLoading === selectedUser.id ? "Deleting..." : "Delete Account"}
                    </Button>
                  </div>
                )}
              </div>
              <Button onClick={() => setSelectedUser(null)}>
                Close Details
              </Button>
            </div>

          </div>
        </div>
      )}

      {/* JOB DETAIL MODAL POPUP */}
      {selectedJob && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-zinc-950/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 w-full max-w-3xl max-h-[85vh] rounded-xl overflow-hidden flex flex-col shadow-2xl animate-scale-up">
            
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/50">
              <div className="space-y-1">
                <h2 className="text-xl font-bold text-zinc-900 dark:text-zinc-50">
                  Discovered Job Detail
                </h2>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  Job ID: #{selectedJob.id} • Registered Owner: {selectedJob.user_name} ({selectedJob.user_email})
                </p>
              </div>
              <button
                onClick={() => setSelectedJob(null)}
                className="h-8 w-8 p-0 rounded-full text-zinc-500 hover:text-zinc-850 dark:hover:text-zinc-200 text-lg font-bold"
              >
                ✕
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              <div className="grid gap-4 sm:grid-cols-2 p-4 border border-zinc-200 dark:border-zinc-800 rounded-lg bg-zinc-50/50 dark:bg-zinc-900/10 text-sm">
                <div className="space-y-1">
                  <p><span className="text-zinc-400">Job Title:</span> <span className="font-semibold text-zinc-900 dark:text-zinc-50">{selectedJob.title}</span></p>
                  <p><span className="text-zinc-400">Company:</span> <span className="font-semibold text-zinc-900 dark:text-zinc-50">{selectedJob.company}</span></p>
                  <p><span className="text-zinc-400">Location:</span> <span className="font-semibold text-zinc-900 dark:text-zinc-50">{selectedJob.location || "N/A"}</span></p>
                </div>
                <div className="space-y-1">
                  <p><span className="text-zinc-400">Platform Source:</span> <span className="font-semibold text-indigo-650 dark:text-indigo-400">{selectedJob.source || "Naukri"}</span></p>
                  <p><span className="text-zinc-400">Date Discovered:</span> <span className="font-semibold text-zinc-900 dark:text-zinc-50">{new Date(selectedJob.created_at).toLocaleString()}</span></p>
                  <p>
                    <span className="text-zinc-400">Status:</span>{" "}
                    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-semibold ${
                      selectedJob.status === "Discovered" ? "bg-blue-50 text-blue-700 dark:bg-blue-950/20 dark:text-blue-400" :
                      selectedJob.status === "Saved" ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/20 dark:text-indigo-400" :
                      selectedJob.status === "Applied" ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-400" :
                      selectedJob.status === "Skipped" ? "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300" :
                      "bg-amber-50 text-amber-700 dark:bg-amber-950/20 dark:text-amber-400"
                    }`}>
                      {selectedJob.status}
                    </span>
                  </p>
                </div>
              </div>

              {selectedJob.match_score !== undefined && selectedJob.match_score !== null && (
                <div className="p-4 border border-zinc-200 dark:border-zinc-800 rounded-lg text-sm">
                  <span className="text-zinc-400 text-xs block font-semibold">Match Score</span>
                  <span className="text-indigo-650 dark:text-indigo-400 text-2xl font-bold">{selectedJob.match_score}%</span>
                </div>
              )}

              <div>
                <h3 className="font-bold text-zinc-800 dark:text-zinc-200 text-sm mb-2 border-b pb-1">
                  Job Description
                </h3>
                <p className="text-xs text-zinc-650 dark:text-zinc-350 leading-relaxed whitespace-pre-line bg-zinc-50 dark:bg-zinc-900/10 p-4 rounded-lg border dark:border-zinc-800/60 font-serif">
                  {selectedJob.description || "No job description provided by platform."}
                </p>
              </div>

              {isValidSupportedJobUrl(selectedJob.apply_url, selectedJob.source) && (
                <div>
                  <h3 className="font-bold text-zinc-800 dark:text-zinc-250 text-sm mb-2">
                    Direct Application Link
                  </h3>
                  <a
                    href={selectedJob.apply_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 text-indigo-650 dark:text-indigo-400 text-xs font-semibold hover:underline bg-indigo-50 dark:bg-indigo-950/20 px-3.5 py-2 rounded-lg border border-indigo-100 dark:border-indigo-900/30 font-mono break-all"
                  >
                    {selectedJob.apply_url}
                    <svg className="h-3.5 w-3.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/50 flex flex-col sm:flex-row sm:justify-between items-center gap-3">
              <div className="flex gap-2">
                <select
                  value={selectedJob.status}
                  onChange={(e) => handleUpdateJobStatus(selectedJob.id, e.target.value as JobStatus)}
                  className="px-2 py-1 bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded text-sm focus:outline-none text-zinc-850 dark:text-zinc-200"
                >
                  <option value="Discovered">Discovered</option>
                  <option value="Saved">Saved</option>
                  <option value="Skipped">Skipped</option>
                </select>
                <span className="text-xs text-zinc-400 self-center">Change status</span>
              </div>
              <Button onClick={() => setSelectedJob(null)}>
                Close Details
              </Button>
            </div>

          </div>
        </div>
      )}
    </div>
  );
}
