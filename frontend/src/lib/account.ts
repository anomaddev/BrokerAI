export const ACCOUNT_UPDATED = "brokerai:account-updated";

export function notifyAccountUpdated() {
  window.dispatchEvent(new Event(ACCOUNT_UPDATED));
}

export function accountDisplayName(user: {
  username: string;
  first_name?: string | null;
  last_name?: string | null;
}): string {
  const parts = [user.first_name?.trim(), user.last_name?.trim()].filter(Boolean) as string[];
  if (parts.length > 0) return parts.join(" ");
  return user.username || "Account";
}

export function accountMenuLabel(user: {
  username: string;
  first_name?: string | null;
}): string {
  const firstName = user.first_name?.trim();
  if (firstName) return firstName;
  return user.username || "Account";
}
