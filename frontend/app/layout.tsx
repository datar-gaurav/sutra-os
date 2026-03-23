import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/layout/app-shell";

export const metadata: Metadata = {
    title: "Sutra — AI Agent Orchestrator",
    description:
        "Orchestrate multiple AI agents with LangChain, Ollama, and Slack integration.",
};

export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html lang="en">
            <body className="flex h-screen overflow-hidden text-stone-800 bg-surface-1">
                <AppShell>{children}</AppShell>
            </body>
        </html>
    );
}
