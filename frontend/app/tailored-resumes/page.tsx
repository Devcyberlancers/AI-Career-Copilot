"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { downloadResumeFromUrl, fetchTailoredResumeHistory, TailoredResume } from "@/services/tailoring";

function scoreValue(item: TailoredResume, primary: "before" | "after" | "improvement"): number | null {
  if (primary === "before") return item.before_score ?? item.original_match_score ?? null;
  if (primary === "after") return item.after_score ?? item.tailored_match_score ?? null;
  return item.improvement ?? item.improvement_score ?? null;
}

function formatScore(value: number | null, signed = false): string {
  if (value === null || value === undefined) return "N/A";
  const rounded = Math.round(value);
  return `${signed && rounded > 0 ? "+" : ""}${rounded}%`;
}

function improvementClass(value: number | null): string {
  if (value === null || value === undefined || value === 0) {
    return "text-zinc-500 dark:text-zinc-400";
  }
  if (value > 0) {
    return "text-emerald-600 dark:text-emerald-400";
  }
  return "text-red-600 dark:text-red-400";
}

function resumeUsedLabel(value?: string | null): string {
  return value === "original" ? "Original" : "Tailored";
}

function resumeUsedClass(value?: string | null): string {
  if (value === "original") {
    return "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200";
  }
  return "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300";
}

export default function TailoredResumesPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const [items, setItems] = useState<TailoredResume[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [downloadingId, setDownloadingId] = useState<number | null>(null);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.push("/login");
  }, [isAuthenticated, isLoading, router]);

  useEffect(() => {
    if (!isAuthenticated) return;
    const loadHistory = async () => {
      setLoading(true);
      setError("");
      try {
        setItems(await fetchTailoredResumeHistory());
      } catch (err: any) {
        setError(err.message || "Could not load tailored resumes.");
      } finally {
        setLoading(false);
      }
    };
    loadHistory();
  }, [isAuthenticated]);

  const handleDownload = async (item: TailoredResume) => {
    setDownloadingId(item.id);
    setError("");
    const resumeUrl = item.pdf_url || item.download_url;
    if (!resumeUrl) {
      setError("Download URL is missing for this tailored resume.");
      setDownloadingId(null);
      return;
    }
    try {
      await downloadResumeFromUrl(resumeUrl, `tailored_resume_${item.id}.pdf`);
    } catch (err: any) {
      setError(err.message || "Could not download tailored resume.");
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <main className="min-h-screen bg-zinc-50 p-6 text-zinc-950 dark:bg-zinc-950 dark:text-zinc-50">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold">My Tailored Resumes</h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">Optimized resume versions created for saved job opportunities.</p>
          </div>
          <Link href="/dashboard">
            <Button variant="outline">Back to Dashboard</Button>
          </Link>
        </div>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">
            {error}
          </div>
        )}

        <Card>
          <CardHeader>
            <CardTitle>History</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="py-10 text-center text-sm text-zinc-500">Loading tailored resumes...</div>
            ) : items.length === 0 ? (
              <div className="py-10 text-center text-sm text-zinc-500">No tailored resumes yet.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1080px] text-left text-sm">
                  <thead className="border-b border-zinc-200 text-xs uppercase text-zinc-500 dark:border-zinc-800">
                    <tr>
                      <th className="py-3 pr-4">Job</th>
                      <th className="py-3 pr-4">Platform</th>
                      <th className="py-3 pr-4">Company</th>
                      <th className="py-3 pr-4">Before</th>
                      <th className="py-3 pr-4">After</th>
                      <th className="py-3 pr-4">Improvement</th>
                      <th className="py-3 pr-4">Resume Used</th>
                      <th className="py-3 pr-4">Match Score</th>
                      <th className="py-3 pr-4">Confidence</th>
                      <th className="py-3 pr-4">Created Date</th>
                      <th className="py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                    {items.map((item) => {
                      const before = scoreValue(item, "before");
                      const after = scoreValue(item, "after");
                      const improvement = scoreValue(item, "improvement");
                      return (
                      <tr key={item.id}>
                        <td className="py-4 pr-4">
                          <div className="font-semibold">{item.job_title || `Job #${item.job_id}`}</div>
                          {(item.reason || item.recommendation) && (
                            <div className="mt-1 max-w-xs text-xs text-zinc-500 dark:text-zinc-400">
                              {item.reason || item.recommendation}
                            </div>
                          )}
                        </td>
                        <td className="py-4 pr-4 text-zinc-600 dark:text-zinc-400">{item.platform || "N/A"}</td>
                        <td className="py-4 pr-4 text-zinc-600 dark:text-zinc-400">{item.company || "N/A"}</td>
                        <td className="py-4 pr-4">{formatScore(before)}</td>
                        <td className="py-4 pr-4">{formatScore(after)}</td>
                        <td className={`py-4 pr-4 font-bold ${improvementClass(improvement)}`}>{formatScore(improvement, true)}</td>
                        <td className="py-4 pr-4">
                          <span className={`rounded-md px-2 py-1 text-xs font-semibold ${resumeUsedClass(item.resume_used)}`}>
                            {resumeUsedLabel(item.resume_used)}
                          </span>
                        </td>
                        <td className="py-4 pr-4">{item.match_score == null ? "N/A" : `${Math.round(item.match_score)}%`}</td>
                        <td className="py-4 pr-4">{item.confidence == null ? "N/A" : `${Math.round(item.confidence)}%`}</td>
                        <td className="py-4 pr-4 text-zinc-600 dark:text-zinc-400">{new Date(item.created_at).toLocaleDateString()}</td>
                        <td className="py-4">
                          <div className="flex justify-end gap-2">
                            <Link href={`/resume-tailoring/${item.job_id}`}>
                              <Button variant="outline" size="sm">View</Button>
                            </Link>
                            <Button size="sm" isLoading={downloadingId === item.id} onClick={() => handleDownload(item)}>
                              Download
                            </Button>
                          </div>
                        </td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
