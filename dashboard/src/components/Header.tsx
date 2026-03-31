"use client";

import { useTheme, useLocale } from "@/lib/providers";

export default function Header() {
  const { theme, toggleTheme } = useTheme();
  const { t, toggleLocale, locale } = useLocale();

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-bg-card/80 backdrop-blur-sm">
      <div className="flex items-center justify-between px-4 h-14">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="text-lg font-bold tracking-tight">
              <span className="text-bull">SMC</span>
              <span className="text-text-primary"> Pulse</span>
            </span>
            <span className="text-xs font-mono text-text-muted">
              <span className="text-bull">USD</span>
              <span className="text-text-muted">/</span>
              <span className="text-bear">JPY</span>
            </span>
          </div>
          <span className="hidden sm:inline text-xs text-text-muted border-l border-border pl-3">
            {t("app.tagline")}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={toggleLocale}
            className="px-2 py-1 text-xs font-medium rounded border border-border
                       text-text-secondary hover:text-text-primary hover:bg-bg-card-hover
                       transition-colors"
          >
            {locale === "en" ? "中文" : "EN"}
          </button>

          <button
            onClick={toggleTheme}
            className="p-1.5 rounded border border-border text-text-secondary
                       hover:text-text-primary hover:bg-bg-card-hover transition-colors"
            title={t("theme.toggle")}
          >
            {theme === "dark" ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="5" />
                <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </header>
  );
}
