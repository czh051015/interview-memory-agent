import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OfferLoop · 面试错题本",
  description: "记得你的面试错题本 Agent",
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
