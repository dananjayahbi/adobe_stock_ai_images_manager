import type { Metadata } from "next";

import UploadTableView from "@/components/uploadTable/UploadTableView";

export const metadata: Metadata = {
  title: "Upload Table · Adobe Stock AI Image Studio",
  description: "Copy/paste-ready metadata rows for Adobe Stock submissions.",
};

interface UploadTablePageProps {
  searchParams?: { token?: string; ids?: string };
}

export default function UploadTablePage({ searchParams }: UploadTablePageProps) {
  const token = searchParams?.token ?? null;
  const idsFromQuery = (searchParams?.ids ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);

  return (
    <main className="min-h-screen px-6 py-8 text-zinc-100">
      <div className="mx-auto max-w-6xl space-y-6">
        <header>
          <h1 className="text-2xl font-bold tracking-tight">Upload Table</h1>
          <p className="text-sm text-zinc-500">
            Copy each field straight into Adobe Stock. Titles, descriptions, and
            keywords are shown in the exact order they were selected.
          </p>
        </header>

        <UploadTableView token={token} idsFromQuery={idsFromQuery} />
      </div>
    </main>
  );
}
