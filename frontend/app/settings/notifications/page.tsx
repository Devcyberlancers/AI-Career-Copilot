"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import {
  ApplicationSettings,
  NotificationSettings,
  fetchApplicationSettings,
  fetchNotificationSettings,
  updateApplicationSettings,
  updateNotificationSettings,
} from "@/services/notifications";

const JOB_PLATFORMS = ["Naukri", "LinkedIn", "Indeed", "Foundit", "Wellfound", "Cutshort", "Hirist"];

const notificationLabels: Record<keyof NotificationSettings, string> = {
  email_notifications: "Email Notifications",
  resume_ready: "Resume Ready",
  job_alerts: "Job Alerts",
  weekly_report: "Weekly Report",
  interview_reminder: "Interview Reminder",
  security_alerts: "Security Alerts",
  marketing_emails: "Marketing Emails",
  application_updates: "Application Updates",
};

export default function NotificationSettingsPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const [settings, setSettings] = useState<NotificationSettings | null>(null);
  const [appSettings, setAppSettings] = useState<ApplicationSettings | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      void Promise.all([fetchNotificationSettings(), fetchApplicationSettings()]).then(([notifications, application]) => {
        setSettings(notifications);
        setAppSettings(application);
      });
    }
  }, [isAuthenticated, isLoading]);

  const save = async () => {
    if (!settings || !appSettings) return;
    await updateNotificationSettings(settings);
    await updateApplicationSettings(appSettings);
    setMessage("Settings saved.");
  };

  if (isLoading || !settings || !appSettings) {
    return <main className="min-h-screen bg-zinc-950 p-8 text-white">Loading settings...</main>;
  }

  return (
    <main className="min-h-screen bg-zinc-950 p-8 text-white">
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Notification Settings</h1>
            <p className="text-sm text-zinc-400">Control email alerts, job updates, and application mode.</p>
          </div>
          <Link className="text-sm text-indigo-300" href="/dashboard">Dashboard</Link>
        </div>

        <Card className="border-zinc-800 bg-zinc-900 text-white">
          <CardHeader>
            <CardTitle>Email Preferences</CardTitle>
            <CardDescription>Choose which career updates should reach your inbox.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            {(Object.keys(notificationLabels) as Array<keyof NotificationSettings>).map((key) => (
              <label key={key} className="flex items-center justify-between rounded-md border border-zinc-800 p-3">
                <span>{notificationLabels[key]}</span>
                <input
                  type="checkbox"
                  checked={settings[key]}
                  onChange={(event) => setSettings({ ...settings, [key]: event.target.checked })}
                />
              </label>
            ))}
          </CardContent>
        </Card>

        <Card className="border-zinc-800 bg-zinc-900 text-white">
          <CardHeader>
            <CardTitle>Application Mode</CardTitle>
            <CardDescription>Automatic mode only applies to saved jobs that match your rules.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <select
              className="w-full rounded-md border border-zinc-700 bg-zinc-950 p-3"
              value={appSettings.mode}
              onChange={(event) => setAppSettings({ ...appSettings, mode: event.target.value as "manual" | "automatic", auto_apply_enabled: event.target.value === "automatic" })}
            >
              <option value="manual">Manual</option>
              <option value="automatic">Automatic</option>
            </select>
            <label className="block text-sm text-zinc-300">
              Minimum Match Score
              <input
                className="mt-2 w-full rounded-md border border-zinc-700 bg-zinc-950 p-3"
                type="number"
                min={0}
                max={100}
                value={appSettings.minimum_match_score}
                onChange={(event) => setAppSettings({ ...appSettings, minimum_match_score: Number(event.target.value) })}
              />
            </label>
            <label className="block text-sm text-zinc-300">
              Maximum Daily Applications
              <input
                className="mt-2 w-full rounded-md border border-zinc-700 bg-zinc-950 p-3"
                type="number"
                min={0}
                max={100}
                value={appSettings.maximum_daily_applications}
                onChange={(event) => setAppSettings({ ...appSettings, maximum_daily_applications: Number(event.target.value) })}
              />
            </label>
          </CardContent>
        </Card>

        <Card className="border-zinc-800 bg-zinc-900 text-white">
          <CardHeader>
            <CardTitle>Daily Job Search Automation</CardTitle>
            <CardDescription>Fetch fresh jobs automatically once per day at your selected time. Each enabled platform can fetch up to 20 jobs.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <label className="flex items-center justify-between rounded-md border border-zinc-800 p-3">
              <span>Enable Daily Search</span>
              <input
                type="checkbox"
                checked={appSettings.daily_job_search_enabled}
                onChange={(event) => setAppSettings({ ...appSettings, daily_job_search_enabled: event.target.checked })}
              />
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-sm text-zinc-300">
                Search Time
                <input
                  className="mt-2 w-full rounded-md border border-zinc-700 bg-zinc-950 p-3"
                  type="time"
                  value={appSettings.daily_job_search_time || "09:00"}
                  onChange={(event) => setAppSettings({ ...appSettings, daily_job_search_time: event.target.value })}
                />
              </label>
              <label className="block text-sm text-zinc-300">
                Jobs Per Platform
                <input
                  className="mt-2 w-full rounded-md border border-zinc-700 bg-zinc-950 p-3"
                  type="number"
                  min={1}
                  max={20}
                  value={appSettings.jobs_per_platform || 20}
                  onChange={(event) => setAppSettings({ ...appSettings, jobs_per_platform: Number(event.target.value) })}
                />
              </label>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {JOB_PLATFORMS.map((platform) => {
                const selected = (appSettings.daily_job_search_platforms || []).includes(platform);
                return (
                  <label key={platform} className="flex items-center justify-between rounded-md border border-zinc-800 p-3 text-sm">
                    <span>{platform}</span>
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={(event) => {
                        const current = appSettings.daily_job_search_platforms || [];
                        setAppSettings({
                          ...appSettings,
                          daily_job_search_platforms: event.target.checked
                            ? [...current, platform]
                            : current.filter((item) => item !== platform),
                        });
                      }}
                    />
                  </label>
                );
              })}
            </div>
          </CardContent>
        </Card>

        <div className="flex items-center gap-4">
          <Button onClick={save}>Save Settings</Button>
          {message && <span className="text-sm text-emerald-300">{message}</span>}
        </div>
      </div>
    </main>
  );
}
