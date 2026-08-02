import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/src/auth/AuthProvider";

export const metadata: Metadata = {
  title: "T-KEIR Workspace",
  description:
    "Search, RAG report generation, and agent dialogs over the T-KEIR corpus",
  icons: {
    icon: [{ url: "/tkeir-logo.png", type: "image/png" }],
    shortcut: "/tkeir-logo.png",
    apple: "/tkeir-logo.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning className="dark">
      <body className="min-h-screen font-sans">
        <AuthProvider>
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
