import { FormEvent, useEffect, useState } from "react";
import { api, profilePhotoUrl } from "../../api/client";
import ProfilePhotoField from "../../components/ProfilePhotoField";
import SettingsPanelHeader from "../../components/SettingsPanelHeader";
import { accountDisplayName, notifyAccountUpdated } from "../../lib/account";
import { notifyProfilePhotoUpdated } from "../../lib/profilePhoto";

type StrengthLevel = "weak" | "fair" | "strong";

function passwordStrength(pw: string): { label: string; level: StrengthLevel; score: number } {
  let score = 0;
  if (pw.length >= 12) score++;
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

export default function AccountTab() {
  const [currentUsername, setCurrentUsername] = useState("");
  const [savedFirstName, setSavedFirstName] = useState("");
  const [savedLastName, setSavedLastName] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [initialHasPhoto, setInitialHasPhoto] = useState(false);
  const [photoVersion, setPhotoVersion] = useState(0);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [removeRequested, setRemoveRequested] = useState(false);
  const [loading, setLoading] = useState(true);

  const [username, setUsername] = useState("");
  const [usernamePassword, setUsernamePassword] = useState("");
  const [usernameSaving, setUsernameSaving] = useState(false);
  const [usernameMessage, setUsernameMessage] = useState("");
  const [usernameError, setUsernameError] = useState("");

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState("");
  const [passwordError, setPasswordError] = useState("");

  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMessage, setProfileMessage] = useState("");
  const [profileError, setProfileError] = useState("");

  useEffect(() => {
    api
      .me()
      .then((user) => {
        setCurrentUsername(user.username);
        setUsername(user.username);
        setSavedFirstName(user.first_name?.trim() ?? "");
        setSavedLastName(user.last_name?.trim() ?? "");
        setFirstName(user.first_name?.trim() ?? "");
        setLastName(user.last_name?.trim() ?? "");
        setInitialHasPhoto(user.has_profile_photo);
        if (user.has_profile_photo) {
          setPhotoVersion(Date.now());
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
    firstName.trim() !== savedFirstName.trim() || lastName.trim() !== savedLastName.trim();
  const profileDirty = photoDirty || namesDirty;
  const usernameChanged = username.trim() !== currentUsername.trim();
  const profileDisplayName = accountDisplayName({
    username: currentUsername,
    first_name: savedFirstName,
    last_name: savedLastName,
  });
  const hasDisplayName = profileDisplayName !== currentUsername;

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

      setProfileMessage("Profile updated.");
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : "Failed to update profile");
    } finally {
      setProfileSaving(false);
    }
  }

  async function saveUsername(e: FormEvent) {
    e.preventDefault();
    if (!usernameChanged || !usernamePassword) return;
    setUsernameError("");
    setUsernameMessage("");
    setUsernameSaving(true);
    try {
      const result = await api.changeUsername({
        username: username.trim(),
        current_password: usernamePassword,
      });
      setCurrentUsername(result.username);
      setUsername(result.username);
      setUsernamePassword("");
      setUsernameMessage("Username updated.");
      notifyAccountUpdated();
    } catch (err) {
      setUsernameError(err instanceof Error ? err.message : "Failed to update username");
    } finally {
      setUsernameSaving(false);
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

  return (
    <div className="settings-panel">
      <SettingsPanelHeader
        title="Account"
        description="Manage your BrokerAI login profile, username, and password."
      />
      <div className="settings-panel-body settings-panel-body--stack">
        {loading ? (
          <p className="settings-muted">Loading account…</p>
        ) : (
          <div className="account-settings">
            <section className="account-section-card">
              <div className="settings-section-intro">
                <h3 className="settings-subsection-title">Profile</h3>
                <p className="settings-panel-desc">
                  Your name and photo appear in the header and user menu across BrokerAI.
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
                      <span className="account-profile-handle">@{currentUsername}</span>
                    </>
                  ) : (
                    <>
                      <span className="account-profile-label">Signed in as</span>
                      <span className="account-profile-username">{currentUsername}</span>
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
                      placeholder="Optional"
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
                      placeholder="Optional"
                    />
                  </label>
                </div>
                <div className="account-form-footer">
                  {profileMessage ? <p className="settings-success">{profileMessage}</p> : null}
                  {profileError ? <p className="settings-error">{profileError}</p> : null}
                  <button
                    className="btn btn-sm"
                    type="submit"
                    disabled={profileSaving || !profileDirty}
                  >
                    {profileSaving ? "Saving…" : "Save profile"}
                  </button>
                </div>
              </form>
            </section>

            <section className="account-section-card">
              <div className="settings-section-intro">
                <h3 className="settings-subsection-title">Username</h3>
                <p className="settings-panel-desc">
                  Lowercase letters, numbers, underscores, and hyphens. Must start with a letter.
                </p>
              </div>
              <form className="settings-form account-form" onSubmit={(e) => void saveUsername(e)}>
                <label htmlFor="account-username">
                  Username
                  <input
                    id="account-username"
                    value={username}
                    onChange={(e) => {
                      setUsername(e.target.value);
                      setUsernameMessage("");
                      setUsernameError("");
                    }}
                    pattern="[a-z][a-z0-9_-]{2,31}"
                    required
                    autoComplete="username"
                    disabled={usernameSaving}
                    spellCheck={false}
                  />
                </label>
                <label htmlFor="account-username-password">
                  Current password
                  <input
                    id="account-username-password"
                    type="password"
                    value={usernamePassword}
                    onChange={(e) => {
                      setUsernamePassword(e.target.value);
                      setUsernameMessage("");
                      setUsernameError("");
                    }}
                    required={usernameChanged}
                    autoComplete="current-password"
                    disabled={usernameSaving}
                  />
                  <span className="settings-field-hint">Required to confirm a username change.</span>
                </label>
                <FormFooter
                  message={usernameMessage}
                  error={usernameError}
                  saving={usernameSaving}
                  saveLabel="Save username"
                  disabled={!usernameChanged || !usernamePassword}
                />
              </form>
            </section>

            <section className="account-section-card">
              <div className="settings-section-intro">
                <h3 className="settings-subsection-title">Password</h3>
                <p className="settings-panel-desc">
                  At least 12 characters with uppercase, lowercase, a digit, and a special character.
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
          </div>
        )}
      </div>
    </div>
  );
}
