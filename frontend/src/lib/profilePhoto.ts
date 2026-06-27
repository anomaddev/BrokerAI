export const PROFILE_PHOTO_UPDATED = "brokerai:profile-photo-updated";

export function notifyProfilePhotoUpdated(): void {
  window.dispatchEvent(new Event(PROFILE_PHOTO_UPDATED));
}
