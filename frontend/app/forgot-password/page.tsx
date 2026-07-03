"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { forgotPassword } from "@/services/auth";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [resetUrl, setResetUrl] = useState<string | null>(null);
  const [error, setError] = useState("");

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const response = await forgotPassword(email);
      const extra = response.outbox_dir ? ` Outbox: ${response.outbox_dir}` : "";
      setMessage(`${response.message}${extra}`);
      setResetUrl(response.reset_url || null);
    } catch (err: any) {
      setError(err.message || "Could not send reset email.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-50 px-4 dark:bg-zinc-950">
      <Card className="w-full max-w-md border-zinc-200 shadow-lg dark:border-zinc-800">
        <CardHeader>
          <CardTitle>Reset your password</CardTitle>
          <CardDescription>Enter your account email and we will send a secure reset link.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            {message && <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-300">{message}</div>}
            {resetUrl && (
              <a href={resetUrl} className="block rounded-md border border-indigo-200 bg-indigo-50 p-3 text-sm font-medium text-indigo-700 hover:underline dark:border-indigo-900/50 dark:bg-indigo-950/30 dark:text-indigo-300">
                Open local reset link
              </a>
            )}
            {error && <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">{error}</div>}
            <div className="space-y-1">
              <Label htmlFor="email">Email Address</Label>
              <Input id="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </div>
            <Button type="submit" className="w-full" isLoading={loading}>Send Reset Link</Button>
          </form>
        </CardContent>
        <CardFooter className="justify-center border-t border-zinc-100 pt-4 dark:border-zinc-900">
          <Link href="/login" className="text-sm font-medium text-indigo-600 hover:underline dark:text-indigo-400">Back to login</Link>
        </CardFooter>
      </Card>
    </main>
  );
}
