"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { authStorage } from "@/lib/auth";
import { Footer } from "./footer";
import { Sidebar } from "./sidebar";

const PUBLIC_ROUTES = ["/login"];

// Routes that render fullscreen without sidebar (e.g. mission-control dashboards)
const STANDALONE_ROUTES = ["/social-pulse"];

// Routes that use the sidebar but want full-width content (e.g. Chat)
const FULL_WIDTH_ROUTES = ["/chat"];

export function AppShell({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const [ready, setReady] = useState(false);
    const isPublic = PUBLIC_ROUTES.includes(pathname);
    const isStandalone = STANDALONE_ROUTES.includes(pathname);
    const isFullWidth = FULL_WIDTH_ROUTES.includes(pathname);

    useEffect(() => {
        if (isPublic) {
            setReady(true);
            return;
        }
        if (!authStorage.isAuthenticated()) {
            router.replace("/login");
        } else {
            setReady(true);
        }
    }, [isPublic, router]);

    if (!ready) {
        return (
            <div className="h-screen flex items-center justify-center bg-surface-1">
                <div className="w-6 h-6 border-2 border-stone-300 border-t-stone-700 rounded-full animate-spin" />
            </div>
        );
    }

    if (isPublic) {
        return (
            <div className="flex w-full h-screen items-center justify-center bg-surface-2">
                {children}
            </div>
        );
    }

    // Standalone pages render fullscreen — no sidebar, no max-width wrapper
    if (isStandalone) {
        return (
            <main className="flex-1 overflow-y-auto custom-scrollbar w-full">
                {children}
            </main>
        );
    }

    return (
        <>
            <Sidebar />
            <main className="flex-1 overflow-y-auto custom-scrollbar flex flex-col">
                {isFullWidth ? (
                    <div className="flex-1 w-full h-full overflow-hidden flex flex-col">
                        {children}
                    </div>
                ) : (
                    <>
                        <div className="flex-1 max-w-7xl mx-auto p-6 lg:p-8 w-full">{children}</div>
                        <Footer />
                    </>
                )}
            </main>
        </>
    );
}
