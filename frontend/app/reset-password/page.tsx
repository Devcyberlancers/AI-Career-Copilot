"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { resetPassword } from "@/services/auth";

function ResetPasswordContent() {
  const token = useSearchParams().get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const response = await resetPassword(token, password);
      setMessage(response.message);
    } catch (err: any) {
      setError(err.message || "Could not reset password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-50 px-4 dark:bg-zinc-950">
      <Card className="w-full max-w-md border-zinc-200 shadow-lg dark:border-zinc-800">
        <CardHeader>
          <CardTitle>Create a new password</CardTitle>
          <CardDescription>This reset link expires after 15 minutes and can be used once.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            {!token && <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">Reset token missing.</div>}
            {message && <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div>}
            {error && <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
            <div className="space-y-1">
              <Label htmlFor="password">New Password</Label>
              <Input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={6} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="confirm">Confirm Password</Label>
              <Input id="confirm" type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)} required minLength={6} />
            </div>
            <Button type="submit" className="w-full" disabled={!token} isLoading={loading}>Reset Password</Button>
          </form>
        </CardContent>
        <CardFooter className="justify-center border-t border-zinc-100 pt-4 dark:border-zinc-900">
          <Link href="/login" className="text-sm font-medium text-indigo-600 hover:underline dark:text-indigo-400">Back to login</Link>
        </CardFooter>
      </Card>
    </main>
  );
}

export default function ResetPasswordPage() {
  return <Suspense fallback={<main className="min-h-screen bg-zinc-950 p-8 text-white">Loading...</main>}><ResetPasswordContent /></Suspense>;
}
