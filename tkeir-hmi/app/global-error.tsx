"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          fontFamily: "system-ui, sans-serif",
          margin: 0,
          minHeight: "100vh",
          padding: 48,
          background: "#0b1220",
          color: "#e8eef7",
        }}
      >
        <div style={{ maxWidth: 512 }}>
          <h1 style={{ fontSize: 22, margin: "0 0 12px" }}>
            Something went wrong
          </h1>
          <p style={{ fontSize: 14, lineHeight: 1.5, opacity: 0.8 }}>
            The workspace hit an unexpected error. You can retry without
            losing the rest of the session.
          </p>
          <button
            type="button"
            onClick={() => reset()}
            style={{
              marginTop: 16,
              padding: "8px 12px",
              borderRadius: 6,
              border: "1px solid #3d4f6f",
              background: "transparent",
              color: "inherit",
              cursor: "pointer",
            }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
