import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Sign In — FinsOpsIQ",
  description: "Sign in with your Microsoft account to access FinsOpsIQ.",
};

export default function LoginLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // Bypass the AppShell — render children in a clean, full-screen container
  return <>{children}</>;
}
