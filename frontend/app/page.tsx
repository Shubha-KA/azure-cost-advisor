import Link from "next/link";
import {
  BarChart3,
  Bot,
  Building2,
  CheckCircle2,
  Gauge,
  Layers3,
  Lightbulb,
  LockKeyhole,
  Search,
  ShieldCheck,
  Sparkles,
  TrendingDown,
} from "lucide-react";

const features = [
  {
    title: "Cost Analytics",
    description: "Understand spend trends, service costs, resource-group costs, and top Azure cost drivers.",
    icon: BarChart3,
  },
  {
    title: "Resource Inventory",
    description: "Discover deployed Azure resources across selected subscriptions with clean FinOps context.",
    icon: Layers3,
  },
  {
    title: "Utilization Insights",
    description: "Correlate utilization signals with cost so teams can identify underused compute resources.",
    icon: Gauge,
  },
  {
    title: "AI Recommendations",
    description: "Ask business questions and receive AI-powered optimization guidance grounded in your Azure data.",
    icon: Bot,
  },
  {
    title: "Multi-Tenant Management",
    description: "Onboard customer tenants and subscriptions with isolated authentication and scoped data access.",
    icon: Building2,
  },
  {
    title: "Azure Cost Optimization",
    description: "Prioritize savings opportunities using costs, inventory, Advisor findings, and utilization metrics.",
    icon: TrendingDown,
  },
];

const steps = [
  "Connect your Azure account",
  "Select subscriptions",
  "Collect Azure cost and resource data",
  "Receive AI-powered optimization recommendations",
];

const benefits = [
  "Reduce cloud spend",
  "Detect unused resources",
  "Optimize AKS workloads",
  "Improve governance",
  "Increase cloud efficiency",
];

const security = [
  "Microsoft Entra ID Authentication",
  "Tenant Isolation",
  "Secure Session Management",
  "Enterprise Ready",
];

export default function Home() {
  return (
    <main className="min-h-screen bg-[#07111f] text-white">
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(37,99,235,0.35),transparent_35%),radial-gradient(circle_at_top_right,rgba(14,165,233,0.22),transparent_30%)]" />
        <div
          className="absolute inset-0 opacity-[0.06]"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,.12) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.12) 1px, transparent 1px)",
            backgroundSize: "56px 56px",
          }}
        />
        <header className="relative mx-auto flex max-w-7xl items-center justify-between px-6 py-6 lg:px-8">
          <Link href="/" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500 shadow-lg shadow-blue-500/25">
              <Sparkles className="h-5 w-5" />
            </div>
            <span className="text-lg font-semibold tracking-tight">FinsOpsIQ</span>
          </Link>
          <Link
            href="/login"
            className="rounded-full border border-white/15 px-4 py-2 text-sm font-medium text-white/90 transition hover:border-blue-300/60 hover:bg-white/10"
          >
            Sign In
          </Link>
        </header>

        <div className="relative mx-auto max-w-7xl px-6 pb-24 pt-16 text-center lg:px-8 lg:pb-32 lg:pt-24">
          <div className="mx-auto mb-6 inline-flex items-center gap-2 rounded-full border border-blue-300/20 bg-blue-400/10 px-4 py-2 text-sm text-blue-100">
            <ShieldCheck className="h-4 w-4" />
            Enterprise Azure FinOps intelligence
          </div>
          <h1 className="mx-auto max-w-5xl text-5xl font-bold tracking-tight sm:text-6xl lg:text-7xl">
            AI-Powered Azure FinOps Platform
          </h1>
          <p className="mx-auto mt-6 max-w-3xl text-lg leading-8 text-slate-300 sm:text-xl">
            Optimize Azure costs, discover waste, analyze utilization, and receive AI-driven recommendations across all your subscriptions.
          </p>
          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Link
              href="/login"
              className="rounded-full bg-blue-500 px-7 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-500/25 transition hover:bg-blue-400"
            >
              Sign In with Microsoft
            </Link>
            <a
              href="#learn-more"
              className="rounded-full border border-white/15 px-7 py-3 text-sm font-semibold text-white transition hover:border-white/35 hover:bg-white/10"
            >
              Learn More
            </a>
          </div>
        </div>
      </section>

      <section id="learn-more" className="bg-slate-950 px-6 py-20 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="mb-12 max-w-3xl">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-300">Platform capabilities</p>
            <h2 className="mt-3 text-3xl font-bold tracking-tight sm:text-4xl">Built for Azure cost visibility and optimization</h2>
          </div>
          <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {features.map(({ title, description, icon: Icon }) => (
              <div key={title} className="rounded-2xl border border-white/10 bg-white/[0.04] p-6 shadow-xl shadow-black/10">
                <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-500/15 text-blue-300">
                  <Icon className="h-6 w-6" />
                </div>
                <h3 className="text-lg font-semibold">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-6 py-20 lg:px-8">
        <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[0.85fr_1.15fr] lg:items-center">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-300">How it works</p>
            <h2 className="mt-3 text-3xl font-bold tracking-tight sm:text-4xl">From connection to recommendations in four steps</h2>
            <p className="mt-4 text-slate-300">
              FinsOpsIQ guides customers through a SaaS-style onboarding flow, validates access, collects FinOps data, and turns it into recommendations your teams can act on.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {steps.map((step, index) => (
              <div key={step} className="rounded-2xl border border-white/10 bg-white/[0.04] p-6">
                <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-blue-500 text-sm font-bold">
                  {index + 1}
                </div>
                <h3 className="font-semibold">{step}</h3>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-slate-950 px-6 py-20 lg:px-8">
        <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-2">
          <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-8">
            <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500/15 text-emerald-300">
              <CheckCircle2 className="h-6 w-6" />
            </div>
            <h2 className="text-3xl font-bold tracking-tight">Benefits</h2>
            <div className="mt-6 grid gap-3">
              {benefits.map((benefit) => (
                <div key={benefit} className="flex items-center gap-3 text-slate-300">
                  <CheckCircle2 className="h-5 w-5 text-emerald-300" />
                  <span>{benefit}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-8">
            <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-500/15 text-blue-300">
              <LockKeyhole className="h-6 w-6" />
            </div>
            <h2 className="text-3xl font-bold tracking-tight">Security</h2>
            <div className="mt-6 grid gap-3">
              {security.map((item) => (
                <div key={item} className="flex items-center gap-3 text-slate-300">
                  <ShieldCheck className="h-5 w-5 text-blue-300" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 py-20 lg:px-8">
        <div className="mx-auto max-w-4xl rounded-3xl border border-blue-300/20 bg-blue-500/10 p-10 text-center shadow-2xl shadow-blue-950/30">
          <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-500">
            <Search className="h-7 w-7" />
          </div>
          <h2 className="text-3xl font-bold tracking-tight">Ready to optimize your Azure spend?</h2>
          <p className="mx-auto mt-4 max-w-2xl text-slate-300">
            Connect with Microsoft Entra ID, select your subscriptions, and let FinsOpsIQ build your FinOps view.
          </p>
          <Link
            href="/login"
            className="mt-8 inline-flex rounded-full bg-white px-7 py-3 text-sm font-semibold text-slate-950 transition hover:bg-blue-50"
          >
            Sign In with Microsoft
          </Link>
        </div>
      </section>
    </main>
  );
}
