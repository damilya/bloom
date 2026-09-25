"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Sun, LineChart, Salad, MessageCircleHeart, Target, FolderInput } from "lucide-react";
import { cx } from "@/lib/format";

const NAV = [
  { href: "/", label: "Today", icon: Sun },
  { href: "/trends", label: "Trends", icon: LineChart },
  { href: "/nutrition", label: "Nutrition", icon: Salad },
  { href: "/coach", label: "Coach", icon: MessageCircleHeart },
  { href: "/goals", label: "Goals", icon: Target },
  { href: "/data", label: "Data", icon: FolderInput },
];

export default function Sidebar() {
  const path = usePathname();
  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));
  return (
    <>
      {/* desktop */}
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-surface/60 px-5 py-8 backdrop-blur lg:flex">
        <Link href="/" className="mb-10 flex items-center gap-2.5 px-2">
          <Logo />
          <span className="font-serif text-2xl tracking-tight">Bloom</span>
        </Link>
        <nav className="flex flex-col gap-1">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cx(
                "flex items-center gap-3 rounded-2xl px-3 py-2.5 text-[15px] transition-colors",
                active(href) ? "bg-sage-soft text-ink font-medium" : "text-muted hover:bg-surface-2 hover:text-ink",
              )}
            >
              <Icon size={18} strokeWidth={1.8} className={active(href) ? "text-sage" : ""} />
              {label}
            </Link>
          ))}
        </nav>
        <p className="mt-auto px-2 text-xs leading-relaxed text-muted">
          Educational tool, not medical advice. In doubt, talk to your doctor.
        </p>
      </aside>
      {/* mobile bottom bar */}
      <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-6 border-t border-line bg-surface/95 px-2 pb-[max(env(safe-area-inset-bottom),8px)] pt-2 backdrop-blur lg:hidden">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} className={cx("flex flex-col items-center gap-0.5 text-[10px]", active(href) ? "text-sage" : "text-muted")}>
            <Icon size={20} strokeWidth={1.8} />
            {label}
          </Link>
        ))}
      </nav>
    </>
  );
}

function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden>
      <circle cx="16" cy="10" r="6" fill="var(--rose)" opacity="0.85" />
      <circle cx="10" cy="19" r="6" fill="var(--sage)" opacity="0.85" />
      <circle cx="22" cy="19" r="6" fill="var(--sand)" opacity="0.9" />
    </svg>
  );
}
