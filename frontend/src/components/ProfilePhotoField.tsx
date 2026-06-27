import { useEffect, useRef, useState } from "react";
import ProfileAvatar from "./ProfileAvatar";

const ACCEPTED_TYPES = "image/jpeg,image/png,image/webp,image/gif";
const MAX_BYTES = 5 * 1024 * 1024;

type ProfilePhotoFieldProps = {
  photoUrl?: string | null;
  previewFile?: File | null;
  onFileSelect: (file: File | null) => void;
  disabled?: boolean;
  size?: number;
};

export default function ProfilePhotoField({
  photoUrl = null,
  previewFile = null,
  onFileSelect,
  disabled = false,
  size = 72,
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

  const displayUrl = previewUrl ?? photoUrl;

  return (
    <div className="profile-photo-field">
      <ProfileAvatar src={displayUrl} size={size} />
      <div className="profile-photo-field-actions">
        <button
          className="btn btn-secondary btn-sm"
          type="button"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
        >
          {displayUrl ? "Change photo" : "Add photo"}
        </button>
        {displayUrl ? (
          <button
            className="btn btn-secondary btn-sm"
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
        <p className="profile-photo-field-hint">Optional. JPEG, PNG, WebP, or GIF up to 5 MB.</p>
        {error ? <p className="profile-photo-field-error">{error}</p> : null}
      </div>
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
