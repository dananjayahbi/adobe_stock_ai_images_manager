import type { Metadata } from "next";

import PlatformComingSoon from "@/components/platforms/PlatformComingSoon";
import { getPlatform } from "@/lib/platforms";

export const metadata: Metadata = { title: "123RF — AI Stock Studio" };

export default function Rf123Page() {
  return <PlatformComingSoon platform={getPlatform("123rf")!} />;
}
