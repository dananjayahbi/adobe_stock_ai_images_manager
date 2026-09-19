import { redirect } from "next/navigation";

/**
 * The dashboard *is* the stages workspace.
 *
 * There is no separate Pipeline page: the Collector is the entry point, so `/`
 * sends the operator straight to Stage 1.
 */
export default function HomePage() {
  redirect("/stages/collector");
}
