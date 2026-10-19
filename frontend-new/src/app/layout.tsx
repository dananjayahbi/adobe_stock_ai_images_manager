import type { Metadata, Viewport } from "next";
import { EB_Garamond, Playfair_Display, Pinyon_Script, Special_Elite } from "next/font/google";
import "./globals.css";

import Header from "@/components/chrome/Header";
import { AuthProvider } from "@/components/auth/AuthProvider";

const display = Playfair_Display({
  subsets: ["latin"],
  variable: "--font-display",
});
const body = EB_Garamond({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "500", "600"],
});
const stamp = Special_Elite({
  subsets: ["latin"],
  variable: "--font-stamp",
  weight: "400",
});
const script = Pinyon_Script({
  subsets: ["latin"],
  variable: "--font-script",
  weight: "400",
});

export const metadata: Metadata = {
  title: "AI Stock Studio — Universal Stock Pipeline",
  description:
    "Local studio for preparing and delivering AI-generated images to stock marketplaces.",
};

export const viewport: Viewport = {
  // Let the page draw under notches/home indicators; the sticky header pads
  // itself clear of the top inset via `.safe-top` (globals.css).
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body
        className={`${display.variable} ${body.variable} ${stamp.variable} ${script.variable} min-h-screen`}
      >
        <AuthProvider>
          <Header />
          {/* pt-5 on <sm: under the two-band header, title + controls +
              folders must not stack ~100px deep. The notch inset lives on
              the sticky header (.safe-top), so it is not re-added here. */}
          <main className="w-full px-4 pb-8 pt-5 sm:px-6 sm:pt-8 lg:px-8 xl:px-10">
            {children}
          </main>
          <footer className="w-full px-4 pb-10 pt-4 sm:px-6 lg:px-8 xl:px-10">
            <div className="divider-dashed flex items-center justify-between pt-4">
              <span className="label-caps">AI Stock Studio</span>
              <span className="label-caps">Est. MMXXVI · Local Pipeline</span>
            </div>
          </footer>
        </AuthProvider>
      </body>
    </html>
  );
}
