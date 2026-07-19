import { useState } from "react";
import { api } from "../../api/client";
import ProfilePhotoField from "../../components/ProfilePhotoField";
import type { SignupDraft } from "./AdminStep";

type ProfilePhotoStepProps = {
  draft: SignupDraft;
  onBack: () => void;
  onComplete: () => void;
};

export default function ProfilePhotoStep({ draft, onBack, onComplete }: ProfilePhotoStepProps) {
  const [profilePhoto, setProfilePhoto] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function finish(photo: File | null) {
    setError("");
    setLoading(true);
    try {
      await api.setup({
        ...draft,
        profile_photo: photo,
      });
      onComplete();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Setup failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="onboarding-welcome onboarding-welcome--photo">
      <div className="onboarding-welcome-main">
        {error && <div className="error">{error}</div>}

        <div className="onboarding-profile-photo">
          <ProfilePhotoField
            previewFile={profilePhoto}
            onFileSelect={setProfilePhoto}
            disabled={loading}
            size={128}
            interactiveAvatar
          >
            <div className="onboarding-welcome-copy">
              <h1>Add a profile photo</h1>
              <p>Tap the image to upload — optional</p>
            </div>
          </ProfilePhotoField>
        </div>
      </div>

      <div className="onboarding-welcome-actions">
        <button
          type="button"
          className="btn btn-secondary onboarding-welcome-cta"
          onClick={onBack}
          disabled={loading}
        >
          Back
        </button>
        <button
          type="button"
          className="btn onboarding-welcome-cta"
          onClick={() => void finish(profilePhoto)}
          disabled={loading}
        >
          {loading ? "Creating…" : profilePhoto ? "Continue" : "Skip for now"}
        </button>
      </div>
    </div>
  );
}
