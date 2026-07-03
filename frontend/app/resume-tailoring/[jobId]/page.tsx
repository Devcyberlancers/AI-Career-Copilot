"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { fetchJobDetails, Job } from "@/services/jobs";
import { downloadResumeFromUrl, downloadTailoredResumeFile, fetchTailoredResumeForJob, TailoredResume } from "@/services/tailoring";

function resolveScore(value: number | null | undefined, fallback?: number | null): number | null {
  return value ?? fallback ?? null;
}

function formatScore(value: number | null): string {
  return value === null || value === undefined ? "N/A" : `${Math.round(value)}%`;
}

function improvementClass(value: number | null): string {
  if (value === null || value === undefined || value === 0) {
    return "border-zinc-200 bg-zinc-50 text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900/30 dark:text-zinc-300";
  }
  if (value > 0) {
    return "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300";
  }
  return "border-red-200 bg-red-50 text-red-700 dark:border-red-900/50 dark:bg-red-950/20 dark:text-red-300";
}

function resumeUsedMessage(value?: string | null): string {
  if (value === "original") {
    return "Your uploaded resume is already more suitable for this position. No optimization was necessary.";
  }
  return "The tailored resume was selected for this position.";
}

function ScoreBar({ label, value }: { label: string; value: number | null }) {
  const displayValue = value ?? 0;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="font-semibold text-zinc-700 dark:text-zinc-200">{label}</span>
        <span className="font-bold text-zinc-950 dark:text-zinc-50">{formatScore(value)}</span>
      </div>
      <div className="h-2 rounded-full bg-zinc-200 dark:bg-zinc-800">
        <div className="h-2 rounded-full bg-indigo-600" style={{ width: `${Math.min(100, Math.max(0, displayValue))}%` }} />
      </div>
    </div>
  );
}

export default function ResumeTailoringPage() {
  const params = useParams<{ jobId: string }>();
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const jobId = Number(params.jobId);

  const [job, setJob] = useState<Job | null>(null);
  const [tailoredResume, setTailoredResume] = useState<TailoredResume | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState<"original" | "tailored" | null>(null);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.push("/login");
  }, [isAuthenticated, isLoading, router]);

  useEffect(() => {
    if (!isAuthenticated || !jobId) return;

    const loadData = async () => {
      setLoading(true);
      setError("");
      try {
        const [jobData, tailoredData] = await Promise.all([
          fetchJobDetails(jobId),
          fetchTailoredResumeForJob(jobId),
        ]);
        setJob(jobData);
        setTailoredResume(tailoredData);
      } catch (err: any) {
        setError(err.message || "Tailoring results are not ready yet.");
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [isAuthenticated, jobId]);

  const matchingSkills = useMemo(() => {
    return job?.matched_skills || [];
  }, [job]);

  const beforeScore = resolveScore(tailoredResume?.before_score, tailoredResume?.original_match_score ?? job?.match_score);
  const afterScore = resolveScore(tailoredResume?.after_score, tailoredResume?.tailored_match_score);
  const improvement = resolveScore(
    tailoredResume?.improvement,
    tailoredResume?.improvement_score ?? (
      beforeScore !== null && afterScore !== null ? afterScore - beforeScore : null
    )
  );

  const handleDownload = async (version: "original" | "tailored") => {
    if (!tailoredResume) return;
    setDownloading(version);
    setError("");
    try {
      if (version === "tailored") {
        const resumeUrl = tailoredResume.pdf_url || tailoredResume.download_url;
        if (!resumeUrl) {
          throw new Error("Download URL is missing for this tailored resume.");
        }
        await downloadResumeFromUrl(resumeUrl, `tailored_resume_${tailoredResume.id}.pdf`);
      } else {
        await downloadTailoredResumeFile(tailoredResume.id, version);
      }
    } catch (err: any) {
      setError(err.message || "Could not download resume.");
    } finally {
      setDownloading(null);
    }
  };

  if (isLoading || loading) {
    return (
      <main className="min-h-screen bg-zinc-50 p-6 dark:bg-zinc-950">
        <div className="mx-auto max-w-6xl">
          <Card>
            <CardContent className="p-10 text-center text-sm text-zinc-500">Loading tailoring results...</CardContent>
          </Card>
        </div>
      </main>
    );
  }

  if (error || !job || !tailoredResume) {
    return (
      <main className="min-h-screen bg-zinc-50 p-6 dark:bg-zinc-950">
        <div className="mx-auto max-w-3xl space-y-4">
          <Card>
            <CardContent className="space-y-4 p-8 text-center">
              <h1 className="text-xl font-bold text-zinc-950 dark:text-zinc-50">Tailoring Results Unavailable</h1>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">{error || "Tailoring is not ready yet."}</p>
              <Link href="/dashboard">
                <Button>Back to Dashboard</Button>
              </Link>
            </CardContent>
          </Card>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-zinc-50 p-6 text-zinc-950 dark:bg-zinc-950 dark:text-zinc-50">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold">{job.title}</h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">{job.company} - {job.location || "Location not specified"}</p>
          </div>
          <Link href="/tailored-resumes">
            <Button variant="outline">My Tailored Resumes</Button>
          </Link>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Match Comparison</CardTitle>
            <CardDescription>Before and after tailoring for this job.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6 md:grid-cols-4">
            <ScoreBar label="Before Tailoring" value={beforeScore} />
            <ScoreBar label="After Tailoring" value={afterScore} />
            <div className={`rounded-lg border p-4 ${improvementClass(improvement)}`}>
              <span className="text-sm font-semibold">Improvement</span>
              <div className="mt-2 text-3xl font-bold">
                {improvement === null ? "N/A" : `${improvement > 0 ? "+" : ""}${Math.round(improvement)}%`}
              </div>
            </div>
            <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
              <span className="text-sm font-semibold text-zinc-600 dark:text-zinc-300">Resume Used</span>
              <div className="mt-2 text-xl font-bold capitalize">{tailoredResume.resume_used || "tailored"}</div>
              <div className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                Confidence: {tailoredResume.confidence == null ? "N/A" : `${Math.round(tailoredResume.confidence)}%`}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-5 text-sm text-zinc-700 dark:text-zinc-300">
            {tailoredResume.reason || tailoredResume.recommendation || resumeUsedMessage(tailoredResume.resume_used)}
          </CardContent>
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Skill Gap</CardTitle>
              <CardDescription>Skills already present and skills to strengthen.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-5 sm:grid-cols-2">
              <div>
                <h3 className="mb-3 text-sm font-bold text-zinc-700 dark:text-zinc-200">Matching Skills</h3>
                <div className="flex flex-wrap gap-2">
                  {matchingSkills.map((skill) => (
                    <span key={skill} className="rounded-md bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300">{skill}</span>
                  ))}
                </div>
              </div>
              <div>
                <h3 className="mb-3 text-sm font-bold text-zinc-700 dark:text-zinc-200">Missing Skills</h3>
                <div className="flex flex-wrap gap-2">
                  {(tailoredResume.missing_keywords?.length ? tailoredResume.missing_keywords : tailoredResume.missing_skills).map((skill) => (
                    <span key={skill} className="rounded-md bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700 dark:bg-amber-950/30 dark:text-amber-300">{skill}</span>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Download</CardTitle>
              <CardDescription>Use the master resume or the optimized version for manual applications.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 sm:flex-row">
              <Button variant="outline" isLoading={downloading === "original"} onClick={() => handleDownload("original")}>
                Download Original Resume
              </Button>
              <Button isLoading={downloading === "tailored"} onClick={() => handleDownload("tailored")}>
                Download Tailored Resume
              </Button>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Resume Comparison</CardTitle>
            <CardDescription>Placeholder comparison ready for n8n-generated content.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
              <h3 className="font-bold">Original Resume</h3>
              <ul className="mt-3 space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
                <li>Summary: General career profile.</li>
                <li>Skills: Broad master skill list.</li>
                <li>Projects: Existing master resume projects.</li>
              </ul>
            </div>
            <div className="rounded-lg border border-indigo-200 bg-indigo-50/50 p-4 dark:border-indigo-900/50 dark:bg-indigo-950/20">
              <h3 className="font-bold">Tailored Resume</h3>
              <ul className="mt-3 space-y-2 text-sm text-zinc-700 dark:text-zinc-300">
                <li>Summary changes: Aligned with {job.title} responsibilities.</li>
                <li>Skill changes: Prioritizes matching skills and highlights gaps.</li>
                <li>Project changes: Positions projects around this job description.</li>
              </ul>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Job Description</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-line text-sm leading-6 text-zinc-700 dark:text-zinc-300">{job.description || "No job description provided."}</p>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
