import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "IAP Planning Module",
  description:
    "2LOD assurance planning — shape a capacity-feasible, signed-off annual assurance plan.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB">
      <body>{children}</body>
    </html>
  );
}
