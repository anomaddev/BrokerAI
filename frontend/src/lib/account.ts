export const ACCOUNT_UPDATED = "brokerai:account-updated";

export function notifyAccountUpdated() {
  window.dispatchEvent(new Event(ACCOUNT_UPDATED));
}

/** Display name is the first name (header, menu, Supabase Studio). */
export function accountDisplayName(user: {
  username: string;
  display_name?: string | null;
  first_name?: string | null;
  email?: string | null;
}): string {
  const display = user.display_name?.trim() || user.first_name?.trim();
  if (display) return display;
  return user.email?.trim() || user.username || "Account";
}

export function accountMenuLabel(user: {
  username: string;
  display_name?: string | null;
  first_name?: string | null;
  email?: string | null;
}): string {
  return accountDisplayName(user);
}
