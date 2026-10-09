import type { Metadata } from "next";
import { EB_Garamond, Playfair_Display, Pinyon_Script, Special_Elite } from "next/font/google";
import "./globals.css";

import Header from "@/components/chrome/Header";

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
  title: "Batch Studio — Adobe Stock Pipeline",
  description:
    "Vintage-styled batch pipeline for processing raster and transparent PNG images for Adobe Stock.",
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
        <Header />
        <main className="w-full px-4 py-8 sm:px-6 lg:px-8 xl:px-10">
          {children}
        </main>
        <footer className="w-full px-4 pb-10 pt-4 sm:px-6 lg:px-8 xl:px-10">
          <div className="divider-dashed flex items-center justify-between pt-4">
            <span className="label-caps">Batch Studio</span>
            <span className="label-caps">Est. MMXXVI · Local Pipeline</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
