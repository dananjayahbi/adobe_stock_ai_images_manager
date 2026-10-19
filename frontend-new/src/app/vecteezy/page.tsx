import type { Metadata } from "next";

import PlatformComingSoon from "@/components/platforms/PlatformComingSoon";
import { getPlatform } from "@/lib/platforms";

export const metadata: Metadata = { title: "Vecteezy — AI Stock Studio" };

export default function VecteezyPage() {
  return <PlatformComingSoon platform={getPlatform("vecteezy")!} />;
}
