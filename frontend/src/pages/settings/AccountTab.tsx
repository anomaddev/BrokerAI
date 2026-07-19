import { FormEvent, useEffect, useState } from "react";
import { api, profilePhotoUrl, type MfaFactor } from "../../api/client";
import MfaEnrollPanel from "../../components/MfaEnrollPanel";
import ProfilePhotoField from "../../components/ProfilePhotoField";
import SettingsPanelHeader from "../../components/SettingsPanelHeader";
import { accountDisplayName, notifyAccountUpdated } from "../../lib/account";
import { notifyProfilePhotoUpdated } from "../../lib/profilePhoto";

type StrengthLevel = "weak" | "fair" | "strong";

function passwordStrength(pw: string): { label: string; level: StrengthLevel; score: number } {
  let score = 0;
  if (pw.length >= 8 && pw.length <= 32) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[a-z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  if (score <= 2) return { label: "Weak", level: "weak", score };
  if (score <= 4) return { label: "Fair", level: "fair", score };
  return { label: "Strong", level: "strong", score };
}

function PasswordStrengthMeter({ password }: { password: string }) {
  const { label, level, score } = passwordStrength(password);

  return (
    <div className="password-strength" aria-live="polite">
      <div className="password-strength-bar" aria-hidden>
        {[1, 2, 3, 4, 5].map((segment) => (
          <span
            key={segment}
            className={`password-strength-segment${segment <= score ? ` active ${level}` : ""}`}
          />
        ))}
      </div>
      <span className={`password-strength-label ${level}`}>Strength: {label}</span>
    </div>
  );
}

function FormFooter({
  message,
  error,
  saving,
  saveLabel,
  disabled,
}: {
  message: string;
  error: string;
  saving: boolean;
  saveLabel: string;
  disabled: boolean;
}) {
  return (
    <div className="account-form-footer">
      {message ? <p className="settings-success">{message}</p> : null}
      {error ? <p className="settings-error">{error}</p> : null}
      <button className="btn btn-sm" type="submit" disabled={saving || disabled}>
        {saving ? "Saving…" : saveLabel}
      </button>
    </div>
  );
}

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return (
    <div className="account-readonly-field">
      <span className="account-readonly-label">{label}</span>
      <span className="account-readonly-value">{value}</span>
    </div>
  );
}

export default function AccountTab() {
  const [authMode, setAuthMode] = useState<"builtin" | "oidc">("builtin");
  const [mfaAvailable, setMfaAvailable] = useState(false);
  const [mfaEnabled, setMfaEnabled] = useState(false);
  const [mfaFactors, setMfaFactors] = useState<MfaFactor[]>([]);
  const [mfaLoading, setMfaLoading] = useState(false);
  const [mfaEnrolling, setMfaEnrolling] = useState(false);
  const [mfaDisablePassword, setMfaDisablePassword] = useState("");
  const [mfaMessage, setMfaMessage] = useState("");
  const [mfaError, setMfaError] = useState("");
  const [mfaSaving, setMfaSaving] = useState(false);
  const [currentUsername, setCurrentUsername] = useState("");
  const [savedEmail, setSavedEmail] = useState("");
  const [savedFirstName, setSavedFirstName] = useState("");
  const [savedLastName, setSavedLastName] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [initialHasPhoto, setInitialHasPhoto] = useState(false);
  const [photoVersion, setPhotoVersion] = useState(0);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [removeRequested, setRemoveRequested] = useState(false);
  const [loading, setLoading] = useState(true);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState("");
  const [passwordError, setPasswordError] = useState("");

  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMessage, setProfileMessage] = useState("");
  const [profileError, setProfileError] = useState("");

  async function refreshMfaStatus() {
    setMfaLoading(true);
    try {
      const status = await api.mfaStatus();
      setMfaAvailable(status.available);
      setMfaEnabled(status.enabled);
      setMfaFactors(status.factors);
    } catch {
      setMfaAvailable(false);
      setMfaEnabled(false);
      setMfaFactors([]);
    } finally {
      setMfaLoading(false);
    }
  }

  useEffect(() => {
    Promise.all([api.authConfig(), api.me()])
      .then(([config, user]) => {
        setAuthMode(config.mode);
        setMfaAvailable(Boolean(config.mfa_available));
        setCurrentUsername(user.username);
        setSavedFirstName(user.first_name?.trim() ?? "");
        setSavedLastName(user.last_name?.trim() ?? "");
        setFirstName(user.first_name?.trim() ?? "");
        setLastName(user.last_name?.trim() ?? "");
        setSavedEmail(user.email?.trim() ?? "");
        setInitialHasPhoto(user.has_profile_photo);
        if (user.has_profile_photo) {
          setPhotoVersion(Date.now());
        }
        if (config.mode === "builtin" && config.mfa_available) {
          void refreshMfaStatus();
        }
      })
      .catch(() => setInitialHasPhoto(false))
      .finally(() => setLoading(false));
  }, []);

  function handleFileSelect(file: File | null) {
    setPendingFile(file);
    setRemoveRequested(file === null && initialHasPhoto);
    setProfileMessage("");
    setProfileError("");
  }

  const photoUrl =
    initialHasPhoto && !removeRequested && !pendingFile ? profilePhotoUrl(photoVersion) : null;
  const photoDirty = Boolean(pendingFile) || removeRequested;
  const namesDirty =
    authMode === "builtin" &&
    (firstName.trim() !== savedFirstName.trim() || lastName.trim() !== savedLastName.trim());
  const profileDirty = photoDirty || namesDirty;
  const signInIdentity = savedEmail || currentUsername;
  const profileDisplayName = accountDisplayName({
    username: signInIdentity,
    first_name: savedFirstName,
  });
  const hasDisplayName = Boolean(savedFirstName.trim());

  async function saveProfile() {
    if (!profileDirty) return;
    setProfileError("");
    setProfileMessage("");
    setProfileSaving(true);
    try {
      if (namesDirty) {
        const result = await api.updateProfile({
          first_name: firstName.trim() || null,
          last_name: lastName.trim() || null,
        });
        const nextFirst = result.first_name?.trim() ?? "";
        const nextLast = result.last_name?.trim() ?? "";
        setSavedFirstName(nextFirst);
        setSavedLastName(nextLast);
        setFirstName(nextFirst);
        setLastName(nextLast);
        notifyAccountUpdated();
      }

      if (photoDirty) {
        if (pendingFile) {
          const result = await api.uploadProfilePhoto(pendingFile);
          setInitialHasPhoto(result.has_profile_photo);
          setPhotoVersion(Date.now());
          setPendingFile(null);
          setRemoveRequested(false);
        } else if (removeRequested) {
          await api.deleteProfilePhoto();
          setInitialHasPhoto(false);
          setPhotoVersion(0);
          setRemoveRequested(false);
        }
        notifyProfilePhotoUpdated();
      }

      setProfileMessage(authMode === "oidc" ? "Profile photo updated." : "Profile updated.");
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : "Failed to update profile");
    } finally {
      setProfileSaving(false);
    }
  }

  async function savePassword(e: FormEvent) {
    e.preventDefault();
    if (!currentPassword || !newPassword || !confirmPassword) return;
    setPasswordError("");
    setPasswordMessage("");
    setPasswordSaving(true);
    try {
      await api.changePassword({
        current_password: currentPassword,
        password: newPassword,
        confirm_password: confirmPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordMessage("Password updated.");
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : "Failed to update password");
    } finally {
      setPasswordSaving(false);
    }
  }

  async function disableMfa(e: FormEvent) {
    e.preventDefault();
    const factorId = mfaFactors[0]?.id;
    if (!factorId || !mfaDisablePassword) return;
    setMfaError("");
    setMfaMessage("");
    setMfaSaving(true);
    try {
      await api.mfaDisable({ password: mfaDisablePassword, factor_id: factorId });
      setMfaDisablePassword("");
      setMfaMessage("Two-factor authentication disabled.");
      await refreshMfaStatus();
    } catch (err) {
      setMfaError(err instanceof Error ? err.message : "Failed to disable 2FA");
    } finally {
      setMfaSaving(false);
    }
  }

  return (
    <div className="settings-panel">
      <SettingsPanelHeader
        title="Account"
        description={
          authMode === "oidc"
            ? "Manage your BrokerAI profile and display preferences. Sign-in is handled by your identity provider."
            : "Manage your BrokerAI profile, email, and password."
        }
      />
      <div className="settings-panel-body settings-panel-body--stack">
        {loading ? (
          <p className="settings-muted">Loading account…</p>
        ) : (
          <div className="account-settings">
            <section className="account-section-card">
              <div className="settings-section-intro">
                <h3 className="settings-subsection-title">Sign-in & identity</h3>
                <p className="settings-panel-desc">
                  {authMode === "oidc"
                    ? "Email and legal name come from your identity provider and refresh when you sign in. Change your password or enable 2FA at your IdP."
                    : "You sign in with your email address. Your name and photo are for display across BrokerAI."}
                </p>
              </div>
              <div className="account-readonly-grid">
                {savedEmail ? (
                  <ReadOnlyField label="Email" value={savedEmail} />
                ) : (
                  <ReadOnlyField label="Sign-in" value={currentUsername} />
                )}
                {authMode === "oidc" && savedFirstName ? (
                  <ReadOnlyField label="First name" value={savedFirstName} />
                ) : null}
                {authMode === "oidc" && savedLastName ? (
                  <ReadOnlyField label="Last name" value={savedLastName} />
                ) : null}
              </div>
            </section>

            <section className="account-section-card">
              <div className="settings-section-intro">
                <h3 className="settings-subsection-title">
                  {authMode === "oidc" ? "Profile photo" : "Profile"}
                </h3>
                <p className="settings-panel-desc">
                  {authMode === "oidc"
                    ? "Your photo appears in the header and user menu. Other display preferences live under Display and General settings."
                    : "Your name and photo appear in the header and user menu across BrokerAI."}
                </p>
              </div>
              <div className="account-profile-row">
                <ProfilePhotoField
                  photoUrl={photoUrl}
                  previewFile={pendingFile}
                  onFileSelect={handleFileSelect}
                  disabled={profileSaving}
                  size={96}
                />
                <div className="account-profile-meta">
                  {hasDisplayName ? (
                    <>
                      <span className="account-profile-display-name">{profileDisplayName}</span>
                      <span className="account-profile-handle">{signInIdentity}</span>
                    </>
                  ) : (
                    <>
                      <span className="account-profile-label">Signed in as</span>
                      <span className="account-profile-username">{signInIdentity}</span>
                    </>
                  )}
                </div>
              </div>
              <form
                className="settings-form account-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  void saveProfile();
                }}
              >
                {authMode === "builtin" ? (
                  <div className="account-name-grid">
                    <label htmlFor="account-first-name">
                      First name
                      <input
                        id="account-first-name"
                        value={firstName}
                        onChange={(e) => {
                          setFirstName(e.target.value);
                          setProfileMessage("");
                          setProfileError("");
                        }}
                        autoComplete="given-name"
                        disabled={profileSaving}
                        maxLength={64}
                        placeholder="Jordan"
                      />
                    </label>
                    <label htmlFor="account-last-name">
                      Last name
                      <input
                        id="account-last-name"
                        value={lastName}
                        onChange={(e) => {
                          setLastName(e.target.value);
                          setProfileMessage("");
                          setProfileError("");
                        }}
                        autoComplete="family-name"
                        disabled={profileSaving}
                        maxLength={64}
                        placeholder="Belfort"
                      />
                    </label>
                  </div>
                ) : null}
                <div className="account-form-footer">
                  {profileMessage ? <p className="settings-success">{profileMessage}</p> : null}
                  {profileError ? <p className="settings-error">{profileError}</p> : null}
                  <button
                    className="btn btn-sm"
                    type="submit"
                    disabled={profileSaving || !profileDirty}
                  >
                    {profileSaving ? "Saving…" : authMode === "oidc" ? "Save photo" : "Save profile"}
                  </button>
                </div>
              </form>
            </section>

            {authMode === "builtin" ? (
              <section className="account-section-card">
                <div className="settings-section-intro">
                  <h3 className="settings-subsection-title">Password</h3>
                  <p className="settings-panel-desc">
                    8–32 characters with uppercase, lowercase, a digit, and a special character.
                  </p>
                </div>
                <form className="settings-form account-form" onSubmit={(e) => void savePassword(e)}>
                  <div className="account-password-grid">
                    <label htmlFor="account-current-password">
                      Current password
                      <input
                        id="account-current-password"
                        type="password"
                        value={currentPassword}
                        onChange={(e) => {
                          setCurrentPassword(e.target.value);
                          setPasswordMessage("");
                          setPasswordError("");
                        }}
                        required
                        autoComplete="current-password"
                        disabled={passwordSaving}
                      />
                    </label>
                    <label htmlFor="account-new-password">
                      New password
                      <input
                        id="account-new-password"
                        type="password"
                        value={newPassword}
                        onChange={(e) => {
                          setNewPassword(e.target.value);
                          setPasswordMessage("");
                          setPasswordError("");
                        }}
                        required
                        autoComplete="new-password"
                        disabled={passwordSaving}
                      />
                      {newPassword ? <PasswordStrengthMeter password={newPassword} /> : null}
                    </label>
                    <label htmlFor="account-confirm-password">
                      Confirm new password
                      <input
                        id="account-confirm-password"
                        type="password"
                        value={confirmPassword}
                        onChange={(e) => {
                          setConfirmPassword(e.target.value);
                          setPasswordMessage("");
                          setPasswordError("");
                        }}
                        required
                        autoComplete="new-password"
                        disabled={passwordSaving}
                      />
                    </label>
                  </div>
                  <FormFooter
                    message={passwordMessage}
                    error={passwordError}
                    saving={passwordSaving}
                    saveLabel="Change password"
                    disabled={!currentPassword || !newPassword || !confirmPassword}
                  />
                </form>
              </section>
            ) : null}

            {authMode === "builtin" && mfaAvailable ? (
              <section className="account-section-card">
                <div className="settings-section-intro">
                  <h3 className="settings-subsection-title">Two-factor authentication</h3>
                  <p className="settings-panel-desc">
                    Optional authenticator app (TOTP). When enabled, sign-in asks for a code after
                    your password.
                  </p>
                </div>
                {mfaLoading ? (
                  <p className="settings-muted">Loading 2FA status…</p>
                ) : mfaEnrolling ? (
                  <MfaEnrollPanel
                    variant="settings"
                    onCancel={() => setMfaEnrolling(false)}
                    onEnabled={() => {
                      setMfaEnrolling(false);
                      setMfaMessage("Two-factor authentication enabled.");
                      void refreshMfaStatus();
                    }}
                  />
                ) : mfaEnabled ? (
                  <form className="settings-form account-form" onSubmit={(e) => void disableMfa(e)}>
                    <p className="settings-muted">
                      Authenticator is on
                      {mfaFactors[0]?.friendly_name
                        ? ` (${mfaFactors[0].friendly_name})`
                        : ""}.
                    </p>
                    <label htmlFor="account-mfa-disable-password">
                      Current password to disable
                      <input
                        id="account-mfa-disable-password"
                        type="password"
                        value={mfaDisablePassword}
                        onChange={(e) => {
                          setMfaDisablePassword(e.target.value);
                          setMfaMessage("");
                          setMfaError("");
                        }}
                        required
                        autoComplete="current-password"
                        disabled={mfaSaving}
                      />
                    </label>
                    <FormFooter
                      message={mfaMessage}
                      error={mfaError}
                      saving={mfaSaving}
                      saveLabel="Disable 2FA"
                      disabled={!mfaDisablePassword}
                    />
                  </form>
                ) : (
                  <div className="account-form-footer">
                    {mfaMessage ? <p className="settings-success">{mfaMessage}</p> : null}
                    {mfaError ? <p className="settings-error">{mfaError}</p> : null}
                    <button
                      type="button"
                      className="btn btn-sm"
                      onClick={() => {
                        setMfaMessage("");
                        setMfaError("");
                        setMfaEnrolling(true);
                      }}
                    >
                      Set up authenticator
                    </button>
                  </div>
                )}
              </section>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
