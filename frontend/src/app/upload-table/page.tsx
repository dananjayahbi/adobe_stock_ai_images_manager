import type { Metadata } from "next";
import { Table2 } from "lucide-react";

import UploadTableView from "@/components/uploadTable/UploadTableView";
import { PageHeader } from "@/components/ui/PageHeader";
import { PageShell } from "@/components/shell/PageShell";

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
    <PageShell>
      <PageHeader
        title="Upload Table"
        tagline="Copy each field straight into Adobe Stock. Titles, descriptions, and keywords are shown in the exact order they were selected."
        icon={<Table2 className="h-5 w-5" aria-hidden />}
      />
      <UploadTableView token={token} idsFromQuery={idsFromQuery} />
    </PageShell>
  );
}
