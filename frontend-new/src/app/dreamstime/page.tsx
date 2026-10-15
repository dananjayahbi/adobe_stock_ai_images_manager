import type { Metadata } from "next";

import PlatformComingSoon from "@/components/platforms/PlatformComingSoon";
import { getPlatform } from "@/lib/platforms";

export const metadata: Metadata = { title: "Dreamstime — AI Stock Studio" };

export default function DreamstimePage() {
  return <PlatformComingSoon platform={getPlatform("dreamstime")!} />;
}
