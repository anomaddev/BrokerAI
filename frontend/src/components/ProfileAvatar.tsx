import { User } from "lucide-react";

type ProfileAvatarProps = {
  src?: string | null;
  alt?: string;
  size?: number;
  className?: string;
};

export default function ProfileAvatar({
  src,
  alt = "Profile photo",
  size = 32,
  className = "",
}: ProfileAvatarProps) {
  const classes = `profile-avatar${className ? ` ${className}` : ""}`;
  const style = { width: size, height: size };

  if (src) {
    return <img src={src} alt={alt} className={classes} style={style} />;
  }

  return (
    <span className={`${classes} profile-avatar--placeholder`} style={style} aria-hidden={!alt}>
      <User size={Math.max(14, Math.round(size * 0.48))} strokeWidth={1.75} />
    </span>
  );
}
