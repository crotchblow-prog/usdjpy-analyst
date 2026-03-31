import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ThemeProvider, LocaleProvider } from "@/lib/providers";
import Header from "@/components/Header";
import { Sidebar, BottomNav } from "@/components/Navigation";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "SMC Pulse — Smart Money Concepts Forex Analysis",
    template: "%s — SMC Pulse",
  },
  description:
    "Real-time Smart Money Concepts analysis for forex trading. Order blocks, fair value gaps, liquidity levels, and scenario projections. Currently covering USD/JPY.",
  metadataBase: new URL("https://smcpulse.com"),
  openGraph: {
    title: "SMC Pulse — Smart Money Concepts Analysis",
    description:
      "Automated forex analysis using ICT/SMC methodology. Order blocks, FVGs, liquidity sweeps, and multi-timeframe playbooks.",
    url: "https://smcpulse.com",
    siteName: "SMC Pulse",
    type: "website",
  },
  robots: {
    index: true,
    follow: true,
  },
  icons: {
    icon: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} dark`}
      suppressHydrationWarning
    >
      <body className="min-h-screen flex flex-col antialiased">
        <ThemeProvider>
          <LocaleProvider>
            <Header />
            <div className="flex flex-1">
              <Sidebar />
              <main className="flex-1 p-4 md:p-6 pb-20 md:pb-6 overflow-auto">
                {children}
              </main>
            </div>
            <BottomNav />
          </LocaleProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
