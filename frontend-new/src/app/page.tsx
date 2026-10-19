import type { Metadata } from "next";

import PlatformPicker from "@/components/platforms/PlatformPicker";

export const metadata: Metadata = {
  title: "Choose a platform — AI Stock Studio",
};

/** The root route: pick which marketplace pipeline to open. */
export default function HomePage() {
  return <PlatformPicker />;
}
