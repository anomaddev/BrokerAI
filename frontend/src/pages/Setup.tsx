import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import ProfilePhotoField from "../components/ProfilePhotoField";

function passwordStrength(pw: string): string {
  let score = 0;
  if (pw.length >= 12) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[a-z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  if (score <= 2) return "Weak";
  if (score <= 4) return "Fair";
  return "Strong";
}

export default function Setup() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"loading" | "builtin" | "oidc">("loading");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [profilePhoto, setProfilePhoto] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api
      .authConfig()
      .then((config) => setMode(config.mode))
      .catch(() => setMode("builtin"));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.setup({
        username,
        password,
        confirm_password: confirm,
        profile_photo: profilePhoto,
      });
      navigate("/");
      window.location.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Setup failed");
    } finally {
      setLoading(false);
    }
  }

  if (mode === "loading") {
    return <div className="center-page">Loading…</div>;
  }

  if (mode === "oidc") {
    return (
      <div className="center-page">
        <div className="auth-card">
          <h1>Welcome to BrokerAI</h1>
          <p>
            Sign in with your identity provider to create your local BrokerAI profile and finish
            setup.
          </p>
          <a className="btn" href="/api/auth/oidc/login" style={{ display: "block", textAlign: "center" }}>
            Continue with SSO
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="center-page">
      <form className="auth-card" onSubmit={onSubmit}>
        <h1>Welcome to BrokerAI</h1>
        <p>Create your admin account. These credentials will also be used for SSH access.</p>
        {error && <div className="error">{error}</div>}
        <div className="field">
          <label>Profile photo</label>
          <ProfilePhotoField
            previewFile={profilePhoto}
            onFileSelect={setProfilePhoto}
            disabled={loading}
          />
        </div>
        <div className="field">
          <label htmlFor="username">Username</label>
          <input
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            pattern="[a-z][a-z0-9_-]{2,31}"
            required
            autoComplete="username"
          />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="new-password"
          />
          {password && <span className="strength">Strength: {passwordStrength(password)}</span>}
        </div>
        <div className="field">
          <label htmlFor="confirm">Confirm password</label>
          <input
            id="confirm"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            autoComplete="new-password"
          />
        </div>
        <button className="btn" type="submit" disabled={loading} style={{ width: "100%" }}>
          {loading ? "Creating…" : "Create account"}
        </button>
      </form>
    </div>
  );
}
