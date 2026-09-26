import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { ApiError, hasAccessToken } from "../../api/client";
import { login } from "../../api/auth";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";

export function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  if (hasAccessToken()) return <Navigate to="/dashboard" replace />;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/dashboard", { replace: true });
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Unable to sign in. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return <main className="flex min-h-screen items-center justify-center bg-kurmesh-polar p-4"><section className="w-full max-w-md rounded-xl border border-kurmesh-border bg-white p-6 shadow-sm sm:p-8" aria-labelledby="login-title"><p className="font-mono text-sm font-bold text-kurmesh-blue">KURMESH / OPERATIONS</p><h1 id="login-title" className="mt-2 text-3xl font-bold text-kurmesh-text">Sign in</h1><p className="mt-2 text-sm text-kurmesh-muted">Access the authenticated maritime decision-support workspace.</p>{error && <Alert className="mt-5" variant="danger" title="Sign-in failed">{error}</Alert>}<form className="mt-6 space-y-5" onSubmit={submit}><label className="block text-sm font-semibold text-kurmesh-text">Email<input aria-label="Email" autoComplete="email" className="mt-2 min-h-11 w-full rounded-lg border border-kurmesh-border px-3" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required disabled={submitting} /></label><label className="block text-sm font-semibold text-kurmesh-text">Password<input aria-label="Password" autoComplete="current-password" className="mt-2 min-h-11 w-full rounded-lg border border-kurmesh-border px-3" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required disabled={submitting} /></label><Button className="w-full" type="submit" loading={submitting}>Sign in securely</Button></form><p className="mt-6 text-xs text-kurmesh-muted">KURMESH supports human-reviewed operational decisions. Signing in does not approve or execute routes.</p></section></main>;
}
