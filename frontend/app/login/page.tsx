"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { authStorage } from "@/lib/auth";

export default function LoginPage() {
    const router = useRouter();
    const [mode, setMode] = useState<"login" | "register">("login");
    const [email, setEmail] = useState("");
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError("");
        setLoading(true);

        try {
            const result =
                mode === "login"
                    ? await authApi.login(email, password)
                    : await authApi.register(email, username, password);

            authStorage.save(result);
            router.replace("/");
        } catch (err: any) {
            setError(err.message || "Something went wrong");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="w-full max-w-md">
            {/* Logo / Title */}
            <div className="text-center mb-8">
                <h1 className="text-3xl font-bold text-stone-800">Sutra</h1>
                <p className="text-stone-500 mt-1 text-sm">AI Agent Orchestrator</p>
            </div>

            <div className="bg-white border border-stone-200 rounded-2xl shadow-sm p-8">
                {/* Tab Toggle */}
                <div className="flex rounded-lg bg-stone-100 p-1 mb-6">
                    <button
                        type="button"
                        onClick={() => { setMode("login"); setError(""); }}
                        className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-colors ${
                            mode === "login"
                                ? "bg-white text-stone-800 shadow-sm"
                                : "text-stone-500 hover:text-stone-700"
                        }`}
                    >
                        Sign In
                    </button>
                    <button
                        type="button"
                        onClick={() => { setMode("register"); setError(""); }}
                        className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-colors ${
                            mode === "register"
                                ? "bg-white text-stone-800 shadow-sm"
                                : "text-stone-500 hover:text-stone-700"
                        }`}
                    >
                        Register
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-1">
                            Email
                        </label>
                        <input
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                            placeholder="you@example.com"
                            className="w-full px-3 py-2 border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-800 focus:border-transparent"
                        />
                    </div>

                    {mode === "register" && (
                        <div>
                            <label className="block text-sm font-medium text-stone-700 mb-1">
                                Username
                            </label>
                            <input
                                type="text"
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                required
                                placeholder="your-username"
                                minLength={3}
                                className="w-full px-3 py-2 border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-800 focus:border-transparent"
                            />
                        </div>
                    )}

                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-1">
                            Password
                        </label>
                        <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            placeholder={mode === "register" ? "Min 8 characters" : "Your password"}
                            minLength={mode === "register" ? 8 : undefined}
                            className="w-full px-3 py-2 border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-800 focus:border-transparent"
                        />
                    </div>

                    {error && (
                        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                            {error}
                        </p>
                    )}

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full py-2 px-4 bg-stone-800 text-white text-sm font-medium rounded-lg hover:bg-stone-700 focus:outline-none focus:ring-2 focus:ring-stone-800 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        {loading
                            ? "Please wait..."
                            : mode === "login"
                            ? "Sign In"
                            : "Create Account"}
                    </button>
                </form>

                {mode === "register" && (
                    <p className="text-xs text-stone-400 text-center mt-4">
                        The first account created becomes the owner.
                    </p>
                )}
            </div>
        </div>
    );
}
