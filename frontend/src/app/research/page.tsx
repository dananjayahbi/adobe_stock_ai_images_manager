import type { Metadata } from "next";

import ResearchPage from "@/components/research/ResearchPage";

export const metadata: Metadata = {
  title: "Prompt Research · Adobe Stock AI Image Studio",
  description:
    "Research a niche with an agent that can search the web, score the idea, and write generation prompts in your house style.",
};

/**
 * The Prompt Research workspace.
 *
 * A route of its own rather than a stage, because it sits *before* Stage 1: the
 * prompts it produces are what the Collector's Prompt Library holds and what the
 * images are generated from.
 */
export default function ResearchRoute() {
  return <ResearchPage />;
}
