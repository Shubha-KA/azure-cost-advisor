"use client";

import { ThemeProvider } from "next-themes";
import { ScopeProvider } from "@/components/scope-provider";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="dark" storageKey="finsopsiq-theme" enableSystem>
      <ScopeProvider>{children}</ScopeProvider>
    </ThemeProvider>
  );
}
