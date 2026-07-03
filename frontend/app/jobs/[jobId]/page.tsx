"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { fetchJobDetails, fetchJobMatchAnalysis, isValidSupportedJobUrl, Job, JobMatchAnalysis } from "@/services/jobs";

function scoreClasses(score: number) {
  if (score >= 90) return "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-300";
  if (score >= 75) return "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900/50 dark:bg-blue-950/30 dark:text-blue-300";
  if (score >= 60) return "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300";
  return "border-red-200 bg-red-50 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300";
}

function EvidenceList({ title, items, tone }: { title: string; items: string[]; tone: "good" | "gap" }) {
  const dot = tone === "good" ? "bg-emerald-500" : "bg-red-500";
  return (
    <div>
      <h3 className="mb-3 text-sm font-bold text-zinc-800 dark:text-zinc-200">{title}</h3>
      {items.length ? (
        <ul className="space-y-2">
          {items.map((item) => (
            <li key={item} className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-300">
              <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} />
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-zinc-500">None detected in the job description.</p>
      )}
    </div>
  );
}

export default function JobDetailsPage() {
  const params = useParams<{ jobId: string }>();
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const [job, setJob] = useState<Job | null>(null);
  const [analysis, setAnalysis] = useState<JobMatchAnalysis | null>(null);
  const [error, setError] = useState("");
  const jobId = Number(params.jobId);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.push("/login");
  }, [isAuthenticated, isLoading, router]);

  useEffect(() => {
    if (!isAuthenticated || !jobId) return;
    Promise.all([fetchJobDetails(jobId), fetchJobMatchAnalysis(jobId)])
      .then(([jobData, analysisData]) => {
        setJob(jobData);
        setAnalysis(analysisData);
      })
      .catch((requestError) => setError(requestError.message || "Could not load this job."));
  }, [isAuthenticated, jobId]);

  if (isLoading || (!job && !error)) {
    return <main className="min-h-screen bg-zinc-50 p-8 text-center text-sm text-zinc-500 dark:bg-zinc-950">Loading match analysis...</main>;
  }

  if (error || !job) {
    return (
      <main className="min-h-screen bg-zinc-50 p-8 dark:bg-zinc-950">
        <div className="mx-auto max-w-3xl">
          <Card><CardContent className="space-y-4 p-8 text-center"><p>{error || "Job not found."}</p><Link href="/dashboard"><Button>Back to Dashboard</Button></Link></CardContent></Card>
        </div>
      </main>
    );
  }

  const score = analysis?.semantic_score ?? job.semantic_score ?? job.match_score ?? 0;
  const breakdown = job.score_breakdown_json || {};

  return (
    <main className="min-h-screen bg-zinc-50 p-6 text-zinc-950 dark:bg-zinc-950 dark:text-zinc-50">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="flex flex-col gap-4 border-b border-zinc-200 pb-6 dark:border-zinc-800 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <Link href="/dashboard" className="text-sm font-semibold text-indigo-600 hover:underline dark:text-indigo-400">Back to Dashboard</Link>
            <h1 className="mt-3 text-2xl font-bold">{job.title}</h1>
            <p className="mt-1 text-sm text-zinc-500">{job.company} - {job.location || "Location not specified"}</p>
          </div>
          <div className={`rounded-md border px-5 py-3 text-center ${scoreClasses(score)}`}>
            <span className="block text-xs font-bold uppercase">Match Score</span>
            <span className="text-3xl font-bold">{Math.round(score)}%</span>
          </div>
        </header>

        <Card>
          <CardHeader><CardTitle>Semantic Similarity</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between text-sm">
              <span className="font-semibold">Candidate profile compared with this job</span>
              <span className="text-xl font-bold">{Math.round(score)}%</span>
            </div>
            <div className="h-3 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
              <div className="h-full rounded-full bg-indigo-600" style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
            </div>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              Model: {analysis?.model || breakdown.model || "Sentence Transformer"}
            </p>
          </CardContent>
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card><CardContent className="grid gap-6 p-6 sm:grid-cols-2"><EvidenceList title="Matched Skills" items={job.matched_skills || []} tone="good" /><EvidenceList title="Missing Skills" items={job.missing_skills || []} tone="gap" /></CardContent></Card>
          <Card><CardContent className="grid gap-6 p-6 sm:grid-cols-2"><EvidenceList title="Matched Tools" items={job.matched_tools || []} tone="good" /><EvidenceList title="Missing Tools" items={job.missing_tools || []} tone="gap" /></CardContent></Card>
        </div>

        <Card>
          <CardHeader><CardTitle>Why This Score Was Assigned</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs font-semibold uppercase text-zinc-500">
              Engine: Hugging Face Sentence Transformer embeddings
            </p>
            <p className="rounded-md border border-zinc-200 p-4 text-sm dark:border-zinc-800">
              {analysis?.explanation || breakdown.explanations?.semantic || "The score is cosine similarity between the candidate and job embeddings."}
            </p>
            {(analysis?.recommendations || breakdown.recommendations || []).length > 0 && (
              <div>
                <h3 className="text-sm font-bold">Recommendations</h3>
                <ul className="mt-2 space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
                  {(analysis?.recommendations || breakdown.recommendations || []).map((recommendation) => (
                    <li key={recommendation}>{recommendation}</li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Job Description</CardTitle></CardHeader>
          <CardContent className="space-y-5">
            <p className="whitespace-pre-line text-sm leading-6 text-zinc-700 dark:text-zinc-300">{job.description || "No job description provided."}</p>
            {isValidSupportedJobUrl(job.apply_url, job.source) && (
              <a href={job.apply_url} target="_blank" rel="noopener noreferrer">
                <Button>Open Job on {job.source || "Source"}</Button>
              </a>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
