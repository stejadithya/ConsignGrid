import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { accentStyle, branding } from "@/config/branding";
import { AuthProvider } from "@/lib/auth";
import { ConfigProvider } from "@/lib/config";

// Inter (variable, 100–900), self-hosted: subset to Latin incl. Māori macrons and the symbols the app uses.
// Licence: ./fonts/Inter-LICENSE.txt (SIL Open Font License 1.1).
const inter = localFont({
  src: "./fonts/InterVariable.woff2",
  weight: "100 900",
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: branding.productName, template: `%s · ${branding.productName}` },
  description: branding.tagline,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={inter.variable} style={accentStyle() as React.CSSProperties}>
      <body>
        <ConfigProvider>
          <AuthProvider>{children}</AuthProvider>
        </ConfigProvider>
      </body>
    </html>
  );
}
