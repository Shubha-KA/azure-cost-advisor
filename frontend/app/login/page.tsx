"use client";

import { useState } from "react";
import { loginUrl } from "@/lib/api";

export default function LoginPage() {
  const [loading, setLoading] = useState(false);

  const handleSignIn = () => {
    setLoading(true);
    window.location.href = loginUrl;
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#0a0e1a]">
      {/* Animated gradient background */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute -left-40 -top-40 h-[600px] w-[600px] animate-pulse rounded-full bg-gradient-to-br from-blue-600/20 to-purple-700/20 blur-3xl" />
        <div className="absolute -bottom-32 -right-32 h-[500px] w-[500px] animate-pulse rounded-full bg-gradient-to-br from-cyan-500/15 to-blue-600/15 blur-3xl [animation-delay:1s]" />
        <div className="absolute left-1/2 top-1/2 h-[400px] w-[400px] -translate-x-1/2 -translate-y-1/2 animate-pulse rounded-full bg-gradient-to-br from-indigo-500/10 to-violet-500/10 blur-3xl [animation-delay:2s]" />
      </div>

      {/* Subtle grid pattern */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.1) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
        }}
      />

      {/* Login card */}
      <div className="relative z-10 w-full max-w-md px-4">
        {/* Glassmorphic card */}
        <div
          className="rounded-2xl border border-white/10 bg-white/[0.04] p-10 shadow-2xl backdrop-blur-xl"
          style={{
            boxShadow:
              "0 0 80px rgba(59,130,246,0.08), 0 25px 50px -12px rgba(0,0,0,0.6)",
          }}
        >
          {/* Logo / Branding */}
          <div className="mb-10 flex flex-col items-center">
            <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 shadow-lg shadow-blue-500/25">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                className="h-8 w-8 text-white"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z"
                />
              </svg>
            </div>
            <h1 className="bg-gradient-to-r from-white to-blue-200 bg-clip-text text-2xl font-bold tracking-tight text-transparent">
              FinsOpsIQ
            </h1>
            <p className="mt-2 text-sm text-slate-400">
              Multi-tenant FinOps intelligence for Azure
            </p>
          </div>

          {/* Divider */}
          <div className="mb-8 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />

          {/* Sign in button */}
          <button
            id="sign-in-microsoft"
            onClick={handleSignIn}
            disabled={loading}
            className="group relative flex w-full items-center justify-center gap-3 rounded-xl border border-white/10 bg-white/[0.06] px-6 py-3.5 text-sm font-semibold text-white transition-all duration-300 hover:border-blue-400/30 hover:bg-white/[0.1] hover:shadow-lg hover:shadow-blue-500/10 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:ring-offset-2 focus:ring-offset-[#0a0e1a] disabled:cursor-wait disabled:opacity-60"
          >
            {loading ? (
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            ) : (
              <>
                {/* Microsoft logo */}
                <svg
                  className="h-5 w-5 transition-transform duration-300 group-hover:scale-110"
                  viewBox="0 0 21 21"
                  fill="none"
                >
                  <rect x="1" y="1" width="9" height="9" fill="#F25022" />
                  <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
                  <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
                  <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
                </svg>
                <span>Sign in with Microsoft</span>
                <svg
                  className="ml-auto h-4 w-4 text-slate-500 transition-all duration-300 group-hover:translate-x-0.5 group-hover:text-white/70"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
                    clipRule="evenodd"
                  />
                </svg>
              </>
            )}
          </button>

          {/* Information text */}
          <p className="mt-6 text-center text-xs text-slate-500">
            Sign in using your Microsoft Entra ID account.
            <br />
            Your organisation&apos;s Azure tenant will be used to identify your
            workspace.
          </p>
        </div>

        {/* Footer */}
        <p className="mt-8 text-center text-[11px] text-slate-600">
          Protected by Microsoft Entra ID &middot; Enterprise SSO
        </p>
      </div>
    </div>
  );
}
