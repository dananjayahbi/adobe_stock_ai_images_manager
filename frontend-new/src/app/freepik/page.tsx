import type { Metadata } from "next";

import PlatformComingSoon from "@/components/platforms/PlatformComingSoon";
import { getPlatform } from "@/lib/platforms";

export const metadata: Metadata = { title: "Freepik — AI Stock Studio" };

export default function FreepikPage() {
  return <PlatformComingSoon platform={getPlatform("freepik")!} />;
}
