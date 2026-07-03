"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmailLogItem, fetchEmailHistory, sendTestEmail } from "@/services/notifications";

export default function EmailHistoryPage() {
  const [logs, setLogs] = useState<EmailLogItem[]>([]);
  const [message, setMessage] = useState("");

  const load = async () => setLogs(await fetchEmailHistory());

  useEffect(() => {
    void load();
  }, []);

  const testEmail = async () => {
    const result = await sendTestEmail("welcome");
    setMessage(result.sent ? "Test email sent." : "Email provider is disabled; test was logged/skipped.");
    await load();
  };

  return (
    <main className="min-h-screen bg-zinc-950 p-8 text-white">
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Email History</h1>
          <Link className="text-sm text-indigo-300" href="/dashboard">Dashboard</Link>
        </div>
        <div className="flex items-center gap-4">
          <Button onClick={testEmail}>Send Test Email</Button>
          {message && <p className="text-sm text-zinc-300">{message}</p>}
        </div>
        <Card className="border-zinc-800 bg-zinc-900 text-white">
          <CardHeader><CardTitle>Recent Emails</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {logs.length === 0 && <p className="text-sm text-zinc-400">No email logs yet.</p>}
            {logs.map((log) => (
              <div key={log.id} className="rounded-md border border-zinc-800 p-3">
                <div className="flex justify-between gap-4">
                  <strong>{log.subject}</strong>
                  <span className="text-sm text-zinc-400">{log.status}</span>
                </div>
                <p className="text-sm text-zinc-400">{log.to_email} ? {log.template_name || "custom"}</p>
                {log.error_message && <p className="text-sm text-red-300">{log.error_message}</p>}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
