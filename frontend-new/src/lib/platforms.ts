export type PlatformStatus = "available" | "coming_soon";

export interface PlatformMeta {
  id: string; // "adobe_stock" | "freepik" | "vecteezy" | "dreamstime" | "123rf" | "wirestock"
  name: string;
  tagline: string;
  status: PlatformStatus;
  route: string; // "/adobe-stock" | "/freepik" | "/vecteezy" | "/dreamstime" | "/123rf" | "/wirestock"
}

/**
 * Frontend platform catalog — mirrors the backend registry contract exactly
 * on ids/routes/status, so the picker and route pages stay in lockstep with
 * the API. Dependency-free by design (no fetch, no imports).
 */
export const PLATFORMS: PlatformMeta[] = [
  {
    id: "adobe_stock",
    name: "Adobe Stock",
    tagline: "The original pipeline — audit, refine, and deliver AI images.",
    status: "available",
    route: "/adobe-stock",
  },
  {
    id: "freepik",
    name: "Freepik",
    tagline: "Vector-first marketplace — illustration and PSD-ready assets.",
    status: "coming_soon",
    route: "/freepik",
  },
  {
    id: "vecteezy",
    name: "Vecteezy",
    tagline: "Vectors & templates, curated for the AI-native creator.",
    status: "coming_soon",
    route: "/vecteezy",
  },
  {
    id: "dreamstime",
    name: "Dreamstime",
    tagline: "The established microstock house — a seasoned second outlet.",
    status: "coming_soon",
    route: "/dreamstime",
  },
  {
    id: "123rf",
    name: "123RF",
    tagline: "Affordable royalty feed — volume-friendly, budget-honest.",
    status: "coming_soon",
    route: "/123rf",
  },
  {
    id: "wirestock",
    name: "Wirestock",
    tagline: "One upload, many markets — the multi-platform distributor.",
    status: "coming_soon",
    route: "/wirestock",
  },
];

export function getPlatform(id: string): PlatformMeta | undefined {
  return PLATFORMS.find((p) => p.id === id);
}
