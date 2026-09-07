import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PointLoop · 申论陪练",
  description: "记得你漏了哪些采分点的申论陪练 Agent",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
