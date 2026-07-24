"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type OkfBundle = {
  bundle_id: string;
  user_space: string;
  query?: string | null;
  concept_count: number;
  created_at?: string;
  path?: string;
};

type BundleDetail = {
  bundle_id: string;
  index_md?: string;
  concepts?: string[];
  bundle?: OkfBundle;
};

function renderMarkdownLite(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\n\n/g, "<br/><br/>");
}

export default function OkfPage() {
  const [bundles, setBundles] = useState<OkfBundle[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<BundleDetail | null>(null);
  const [conceptId, setConceptId] = useState<string | null>(null);
  const [conceptMd, setConceptMd] = useState<string>("");
  const [query, setQuery] = useState("Objective ALPHA");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshList = useCallback(async () => {
    const res = await fetch("/api/okf/okf/bundles", { cache: "no-store" });
    if (!res.ok) {
      throw new Error(await res.text());
    }
    const body = (await res.json()) as { bundles?: OkfBundle[] };
    setBundles(body.bundles ?? []);
  }, []);

  useEffect(() => {
    void refreshList().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "list failed");
    });
  }, [refreshList]);

  async function openBundle(id: string) {
    setSelected(id);
    setConceptId(null);
    setConceptMd("");
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/okf/okf/bundles/${encodeURIComponent(id)}`, {
        cache: "no-store",
      });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      setDetail((await res.json()) as BundleDetail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "load failed");
    } finally {
      setBusy(false);
    }
  }

  async function openConcept(id: string) {
    if (!selected) {
      return;
    }
    setConceptId(id);
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/okf/okf/bundles/${encodeURIComponent(selected)}?concept_id=${encodeURIComponent(id)}`,
        { cache: "no-store" },
      );
      // Server returns full payload; concept markdown via MCP-style fields.
      // Prefer dedicated concept fetch through list payload fallback.
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const body = (await res.json()) as {
        markdown?: string;
        concepts?: string[];
        index_md?: string;
      };
      if (body.markdown) {
        setConceptMd(body.markdown);
      } else {
        // Fallback: re-fetch via export path is not available; show index note
        setConceptMd(
          `# ${id}\n\nOpen via MCP okf_bundle_get or download the bundle.`,
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "concept failed");
    } finally {
      setBusy(false);
    }
  }

  async function generateBundle() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/okf/okf/export", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          query: query.trim() || null,
          max_docs: 20,
        }),
      });
      const body = (await res.json()) as {
        bundle?: OkfBundle;
        detail?: string;
      };
      if (!res.ok || !body.bundle) {
        throw new Error(body.detail || `export failed (${res.status})`);
      }
      await refreshList();
      await openBundle(body.bundle.bundle_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "export failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-primary">
            T-KEIR
          </p>
          <h1 className="text-2xl font-bold tracking-tight">OKF Bundles</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Browse and generate OKF v0.1 knowledge bundles for your user_space.
          </p>
        </div>
        <div className="flex gap-3 text-sm">
          <Link href="/" className="text-primary underline-offset-2 hover:underline">
            RAG
          </Link>
          <Link
            href="/agents"
            className="text-primary underline-offset-2 hover:underline"
          >
            Agents
          </Link>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Generate bundle from query</CardTitle>
          <CardDescription>
            Optional query scopes the export via RAG. Leave blank for a full
            static export (capped by max_docs on the server).
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex-1 space-y-1 text-sm">
            <span className="text-muted-foreground">Query</span>
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={busy}
              placeholder="What is the status of Project ATLAS?"
            />
          </label>
          <Button onClick={() => void generateBundle()} disabled={busy}>
            Generate
          </Button>
        </CardContent>
      </Card>

      {error ? (
        <p className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Bundles</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {bundles.length === 0 ? (
              <p className="text-sm text-muted-foreground">No bundles yet.</p>
            ) : (
              bundles.map((b) => (
                <button
                  key={b.bundle_id}
                  type="button"
                  onClick={() => void openBundle(b.bundle_id)}
                  className={`w-full rounded-md border px-3 py-2 text-left text-sm transition ${
                    selected === b.bundle_id
                      ? "border-primary bg-primary/5"
                      : "hover:bg-muted/40"
                  }`}
                >
                  <div className="font-medium truncate">{b.bundle_id}</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    <Badge variant="secondary">{b.concept_count} concepts</Badge>
                    {b.query ? <Badge variant="outline">scoped</Badge> : null}
                  </div>
                </button>
              ))
            )}
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => void refreshList()}
              disabled={busy}
            >
              Refresh
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-2">
            <div>
              <CardTitle className="text-base">
                {selected ? selected : "Select a bundle"}
              </CardTitle>
              <CardDescription>
                Index, concepts, and download.
              </CardDescription>
            </div>
            {selected ? (
              <Button asChild variant="secondary" size="sm">
                <a
                  href={`/api/okf/okf/bundles/${encodeURIComponent(selected)}/download`}
                >
                  Download
                </a>
              </Button>
            ) : null}
          </CardHeader>
          <CardContent>
            {!detail ? (
              <p className="text-sm text-muted-foreground">
                Choose a bundle from the list.
              </p>
            ) : (
              <Tabs defaultValue="index">
                <TabsList>
                  <TabsTrigger value="index">Index</TabsTrigger>
                  <TabsTrigger value="concepts">Concepts</TabsTrigger>
                  <TabsTrigger value="concept" disabled={!conceptId}>
                    Concept
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="index" className="prose prose-sm max-w-none">
                  <div
                    dangerouslySetInnerHTML={{
                      __html: renderMarkdownLite(detail.index_md || ""),
                    }}
                  />
                </TabsContent>
                <TabsContent value="concepts" className="space-y-2">
                  {(detail.concepts || []).map((cid) => (
                    <button
                      key={cid}
                      type="button"
                      className="block w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-muted/40"
                      onClick={() => void openConcept(cid)}
                    >
                      {cid}
                    </button>
                  ))}
                </TabsContent>
                <TabsContent value="concept" className="prose prose-sm max-w-none">
                  <div
                    dangerouslySetInnerHTML={{
                      __html: renderMarkdownLite(conceptMd),
                    }}
                  />
                </TabsContent>
              </Tabs>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
