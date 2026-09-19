import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

import NavBar from "@/components/NavBar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Adobe Stock AI Image Studio",
  description: "Local pipeline for auditing and preparing AI-generated images for Adobe Stock.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} min-h-screen bg-navy-900 text-navy-50 antialiased`}>
        <NavBar />
        {children}
      </body>
    </html>
  );
}
