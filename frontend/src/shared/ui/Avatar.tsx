import { useState } from "react";
import { BASE_URL } from "../api/client";
import { identityColor } from "../lib/identity";

function initialsFor(name: string): string {
  const parts = name.trim().split(/\s+/);
  return parts
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

/** A person's photo, or their initials on a colour picked from their
 *  name, from the same palette as job badges. `src` is the avatar_url the API hands out beside a name (a path
 *  relative to the API); a photo that fails to load falls back to the
 *  initials rather than a broken-image icon. */
export function Avatar({ name, size = 36, src }: { name: string; size?: number; src?: string | null }) {
  const [failed, setFailed] = useState<string | null>(null);
  const showPhoto = !!src && failed !== src;

  if (showPhoto) {
    return (
      <img
        src={`${BASE_URL}${src}`}
        alt=""
        width={size}
        height={size}
        onError={() => setFailed(src)}
        style={{
          width: size,
          height: size,
          borderRadius: "50%",
          objectFit: "cover",
          flexShrink: 0,
          display: "block",
          background: "var(--surface-bg-alt)",
        }}
      />
    );
  }

  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: identityColor(name),
        color: "white",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "var(--arkive-font)",
        fontSize: size * 0.4,
        fontWeight: 700,
        flexShrink: 0,
      }}
    >
      {initialsFor(name)}
    </div>
  );
}
