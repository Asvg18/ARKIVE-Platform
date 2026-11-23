import { useEffect, useState } from "react";
import { fetchFileBlobUrl } from "../api/client";
import { Button } from "../ui/Button";

/**
 * An inline PDF viewer behind a toggle button, for a file the backend
 * only serves as an authenticated download. A plain `<iframe src="...">`
 * can't carry an Authorization header, so this fetches the file as a
 * blob first (see fetchFileBlobUrl) and points the iframe at that
 * instead -- an authenticated fetch, not a raw src to the API path.
 *
 * Sits beside the existing download button, not in place of it --
 * previewing and keeping a copy are different things to want.
 */
export function PdfPreview({
  path,
  token,
  label = "Preview",
}: {
  path: string;
  token: string | null;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Revoked on unmount (or if this ever fetches a second blob) -- an
  // object URL otherwise pins the underlying data in memory for the rest
  // of the tab's life, not just while the preview is open.
  useEffect(() => {
    return () => {
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [blobUrl]);

  async function handleToggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    // Fetched once and kept -- reopening after a collapse should be
    // instant, not a second round trip for a file that hasn't changed.
    if (blobUrl || loading) return;
    setLoading(true);
    setError(null);
    try {
      setBlobUrl(await fetchFileBlobUrl(path, token, "Could not load the preview."));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the preview.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <Button variant="ghost" onClick={handleToggle} style={{ padding: "6px 12px", fontSize: "var(--text-sm)" }}>
        {open ? "Hide Preview" : label}
      </Button>
      {open && (
        <div style={{ marginTop: 10 }}>
          {loading && (
            <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "var(--ink-600)", margin: 0 }}>
              Loading preview…
            </p>
          )}
          {error && (
            <p style={{ fontFamily: "var(--arkive-font)", fontSize: "var(--text-sm)", color: "crimson", margin: 0 }}>
              {error}
            </p>
          )}
          {blobUrl && !loading && !error && (
            <iframe
              src={blobUrl}
              title="PDF preview"
              style={{
                display: "block",
                width: "100%",
                height: 600,
                border: "1px solid var(--surface-border)",
                borderRadius: "var(--radius)",
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}
