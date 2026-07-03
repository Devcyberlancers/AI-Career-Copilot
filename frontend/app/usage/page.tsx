"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { UsageLimitItem, fetchUsageLimits } from "@/services/notifications";

export default function UsageStatisticsPage() {
  const [limits, setLimits] = useState<UsageLimitItem[]>([]);

  useEffect(() => {
    void fetchUsageLimits().then(setLimits);
  }, []);

  return (
    <main className="min-h-screen bg-zinc-950 p-8 text-white">
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Daily Limits</h1>
          <Link className="text-sm text-indigo-300" href="/dashboard">Dashboard</Link>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {limits.map((item) => (
            <Card key={item.platform} className="border-zinc-800 bg-zinc-900 text-white">
              <CardHeader><CardTitle className="text-base">{item.platform}</CardTitle></CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">{item.used} / {item.limit}</p>
                <p className="text-sm text-zinc-400">Remaining: {item.remaining}</p>
                <p className="mt-2 text-xs text-zinc-500">Reset: {new Date(item.reset_at).toLocaleString()}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </main>
  );
}
