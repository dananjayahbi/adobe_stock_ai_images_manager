import type { Metadata } from "next";

import PlatformComingSoon from "@/components/platforms/PlatformComingSoon";
import { getPlatform } from "@/lib/platforms";

export const metadata: Metadata = { title: "Wirestock — AI Stock Studio" };

export default function WirestockPage() {
  return <PlatformComingSoon platform={getPlatform("wirestock")!} />;
}
