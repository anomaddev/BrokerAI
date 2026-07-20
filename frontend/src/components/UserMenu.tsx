import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, LogOut, User } from "lucide-react";
import { api, PROFILE_PHOTO_PATH, profilePhotoUrl } from "../api/client";
import ProfileAvatar from "./ProfileAvatar";
import { PROFILE_PHOTO_UPDATED } from "../lib/profilePhoto";
import { ACCOUNT_UPDATED, accountMenuLabel } from "../lib/account";

type UserMenuProps = {
  displayName: string;
  profilePhotoUrlValue?: string | null;
  photoVersion?: number;
  authMode?: "builtin" | "oidc";
};

export default function UserMenu({
  displayName,
  profilePhotoUrlValue = null,
  photoVersion = 0,
  authMode = "builtin",
}: UserMenuProps) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function handleClick(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  async function logout() {
    const result =
      authMode === "oidc" ? await api.oidcLogout() : await api.logout();
    if (result.logout_url) {
      window.location.href = result.logout_url;
      return;
    }
    window.location.href = authMode === "oidc" ? "/api/auth/oidc/login" : "/login";
  }

  const menuLabel = displayName || "Account";
  const avatarSrc = profilePhotoUrl(profilePhotoUrlValue, photoVersion);

  return (
    <div className="user-menu" ref={menuRef}>
      <button
        type="button"
        className="user-menu-trigger"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <ProfileAvatar src={avatarSrc} alt="" size={28} />
        <span className="user-menu-username">{menuLabel}</span>
        <ChevronDown
          size={16}
          strokeWidth={2}
          className={`user-menu-chevron${open ? " open" : ""}`}
          aria-hidden
        />
      </button>
      {open ? (
        <div className="user-menu-dropdown" role="menu">
          <Link
            to="/settings/account"
            className="user-menu-item"
            role="menuitem"
            onClick={() => setOpen(false)}
          >
            <User size={16} strokeWidth={1.75} aria-hidden />
            Account Settings
          </Link>
          <button
            type="button"
            className="user-menu-item user-menu-item--danger"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              void logout();
            }}
          >
            <LogOut size={16} strokeWidth={1.75} aria-hidden />
            Logout
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function UserMenuContainer() {
  const [displayName, setDisplayName] = useState("");
  const [profilePhotoUrlValue, setProfilePhotoUrlValue] = useState<string | null>(null);
  const [photoVersion, setPhotoVersion] = useState(0);
  const [authMode, setAuthMode] = useState<"builtin" | "oidc">("builtin");

  useEffect(() => {
    function loadProfile() {
      api
        .authConfig()
        .then((config) => setAuthMode(config.mode))
        .catch(() => setAuthMode("builtin"));

      api
        .me()
        .then((user) => {
          setDisplayName(accountMenuLabel(user));
          const url =
            user.profile_photo_url ?? (user.has_profile_photo ? PROFILE_PHOTO_PATH : null);
          setProfilePhotoUrlValue(url);
          if (url) {
            setPhotoVersion(Date.now());
          }
        })
        .catch(() => {
          setDisplayName("");
          setProfilePhotoUrlValue(null);
        });
    }

    loadProfile();
    window.addEventListener(PROFILE_PHOTO_UPDATED, loadProfile);
    window.addEventListener(ACCOUNT_UPDATED, loadProfile);
    return () => {
      window.removeEventListener(PROFILE_PHOTO_UPDATED, loadProfile);
      window.removeEventListener(ACCOUNT_UPDATED, loadProfile);
    };
  }, []);

  return (
    <UserMenu
      displayName={displayName}
      profilePhotoUrlValue={profilePhotoUrlValue}
      photoVersion={photoVersion}
      authMode={authMode}
    />
  );
}
