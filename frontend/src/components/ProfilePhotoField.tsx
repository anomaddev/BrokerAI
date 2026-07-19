import { useEffect, useRef, useState, type ReactNode } from "react";
import { Camera } from "lucide-react";
import ProfileAvatar from "./ProfileAvatar";

const ACCEPTED_TYPES = "image/jpeg,image/png,image/webp,image/gif";
const MAX_BYTES = 5 * 1024 * 1024;

type ProfilePhotoFieldProps = {
  photoUrl?: string | null;
  previewFile?: File | null;
  onFileSelect: (file: File | null) => void;
  disabled?: boolean;
  size?: number;
  /** Avatar opens the file picker; hides Add/Change buttons. */
  interactiveAvatar?: boolean;
  /** Rendered between the avatar and action buttons (e.g. title copy). */
  children?: ReactNode;
};

export default function ProfilePhotoField({
  photoUrl = null,
  previewFile = null,
  onFileSelect,
  disabled = false,
  size = 72,
  interactiveAvatar = false,
  children,
}: ProfilePhotoFieldProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!previewFile) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(previewFile);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [previewFile]);

  function handleChange(file: File | null) {
    setError("");
    if (!file) {
      onFileSelect(null);
      return;
    }
    if (!file.type.startsWith("image/")) {
      setError("Choose a JPEG, PNG, WebP, or GIF image.");
      onFileSelect(null);
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("Profile photo must be 5 MB or smaller.");
      onFileSelect(null);
      return;
    }
    onFileSelect(file);
  }

  function openPicker() {
    if (disabled) return;
    inputRef.current?.click();
  }

  const displayUrl = previewUrl ?? photoUrl;
  const avatarLabel = displayUrl ? "Change profile photo" : "Add profile photo";

  const avatar = interactiveAvatar ? (
    <button
      type="button"
      className={`profile-photo-avatar-btn${displayUrl ? " has-photo" : ""}`}
      onClick={openPicker}
      disabled={disabled}
      aria-label={avatarLabel}
    >
      <ProfileAvatar src={displayUrl} size={size} />
      <span className="profile-photo-avatar-overlay" aria-hidden>
        <Camera size={Math.max(18, Math.round(size * 0.22))} strokeWidth={2} />
      </span>
    </button>
  ) : (
    <ProfileAvatar src={displayUrl} size={size} />
  );

  const showActions = !interactiveAvatar || Boolean(displayUrl) || Boolean(error);

  return (
    <div className={`profile-photo-field${interactiveAvatar ? " profile-photo-field--interactive" : ""}`}>
      {avatar}
      {children}
      {showActions ? (
        <div className="profile-photo-field-actions">
          {!interactiveAvatar ? (
            <button
              className="btn btn-secondary btn-sm"
              type="button"
              disabled={disabled}
              onClick={openPicker}
            >
              {displayUrl ? "Change photo" : "Add photo"}
            </button>
          ) : null}
          {displayUrl ? (
            <button
              className={interactiveAvatar ? "profile-photo-remove" : "btn btn-secondary btn-sm"}
              type="button"
              disabled={disabled}
              onClick={() => {
                handleChange(null);
                if (inputRef.current) inputRef.current.value = "";
              }}
            >
              Remove
            </button>
          ) : null}
          {!interactiveAvatar ? (
            <p className="profile-photo-field-hint">Optional. JPEG, PNG, WebP, or GIF up to 5 MB.</p>
          ) : null}
          {error ? <p className="profile-photo-field-error">{error}</p> : null}
        </div>
      ) : null}
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_TYPES}
        className="profile-photo-field-input"
        disabled={disabled}
        onChange={(event) => handleChange(event.target.files?.[0] ?? null)}
      />
    </div>
  );
}
