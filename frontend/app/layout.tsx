import type { Metadata } from "next";
import { Noto_Sans_SC, Noto_Serif_SC } from "next/font/google";

import "./globals.css";

const sans = Noto_Sans_SC({
  subsets: ["latin"],
  variable: "--font-sans",
  weight: ["400", "500", "700"]
});

const serif = Noto_Serif_SC({
  subsets: ["latin"],
  variable: "--font-serif",
  weight: ["500", "700"]
});

export const metadata: Metadata = {
  title: "QA Evaluate",
  description: "QA pair evaluation platform"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
<<<<<<< HEAD
    <html lang="zh-CN" suppressHydrationWarning>
      <body
        className={`${sans.variable} ${serif.variable} font-sans`}
        suppressHydrationWarning
      >
=======
    <html lang="zh-CN">
      <body className={`${sans.variable} ${serif.variable} font-sans`}>
>>>>>>> 26fc7231bbdd932be6ae9e34e895ee67ca3d7fda
        {children}
      </body>
    </html>
  );
}
