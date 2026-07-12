"use client";

import { Loader2, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Language } from "@/lib/types";

interface SearchHeaderProps {
  query: string;
  language: Language;
  hits: number;
  loading: boolean;
  onQueryChange: (value: string) => void;
  onLanguageChange: (value: Language) => void;
  onHitsChange: (value: number) => void;
  onSubmit: () => void;
}

export function SearchHeader({
  query,
  language,
  hits,
  loading,
  onQueryChange,
  onLanguageChange,
  onHitsChange,
  onSubmit,
}: SearchHeaderProps) {
  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit();
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border bg-card p-4 shadow-sm"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
        <div className="flex-1 space-y-2">
          <label
            htmlFor="rag-query"
            className="text-sm font-medium text-muted-foreground"
          >
            Natural language question
          </label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="rag-query"
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder='e.g. "What did Acme launch?"'
              className="pl-10"
              disabled={loading}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:w-auto">
          <div className="space-y-2">
            <label
              htmlFor="rag-language"
              className="text-sm font-medium text-muted-foreground"
            >
              Language
            </label>
            <Select
              value={language}
              onValueChange={(value) => onLanguageChange(value as Language)}
              disabled={loading}
            >
              <SelectTrigger id="rag-language" className="w-full min-w-[7rem]">
                <SelectValue placeholder="Language" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">English</SelectItem>
                <SelectItem value="fr">Français</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <label
              htmlFor="rag-hits"
              className="text-sm font-medium text-muted-foreground"
            >
              Max hits
            </label>
            <Input
              id="rag-hits"
              type="number"
              min={1}
              max={100}
              value={hits}
              onChange={(event) => {
                const parsed = Number.parseInt(event.target.value, 10);
                if (!Number.isNaN(parsed)) {
                  onHitsChange(Math.min(100, Math.max(1, parsed)));
                }
              }}
              disabled={loading}
            />
          </div>

          <div className="col-span-2 sm:col-span-1">
            <Button
              type="submit"
              className="mt-7 w-full lg:mt-0"
              disabled={loading || query.trim().length === 0}
            >
              {loading ? (
                <>
                  <Loader2 className="animate-spin" />
                  Searching…
                </>
              ) : (
                <>
                  <Search />
                  Search
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </form>
  );
}
