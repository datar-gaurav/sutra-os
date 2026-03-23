/** @type {import('tailwindcss').Config} */
module.exports = {
    darkMode: "class",
    content: [
        "./app/**/*.{js,ts,jsx,tsx,mdx}",
        "./components/**/*.{js,ts,jsx,tsx,mdx}",
    ],
    theme: {
        extend: {
            colors: {
                brand: {
                    50: "#faf8f5",
                    100: "#f0ebe4",
                    200: "#e2d9cc",
                    300: "#cfc1ad",
                    400: "#b8a48a",
                    500: "#a08968",
                    600: "#8b7355",
                    700: "#735f47",
                    800: "#5e4d3b",
                    900: "#4d4032",
                    950: "#2a221a",
                },
                surface: {
                    0: "#ffffff",
                    1: "#FAF8F5",
                    2: "#F5F0EB",
                    3: "#EBE5DD",
                    dark0: "#1a1816",
                    dark1: "#242120",
                    dark2: "#2e2b28",
                    dark3: "#3d3935",
                },
                accent: {
                    success: "#10b981",
                    warning: "#f59e0b",
                    error: "#ef4444",
                    info: "#3b82f6",
                },
            },
            fontFamily: {
                sans: ["-apple-system", "BlinkMacSystemFont", "SF Pro Display", "Segoe UI", "Roboto", "Helvetica", "Arial", "sans-serif"],
                mono: ["SFMono-Regular", "Menlo", "Monaco", "Consolas", "Liberation Mono", "Courier New", "monospace"],
            },
            animation: {
                "fade-in": "fadeIn 0.5s ease-out",
                "slide-up": "slideUp 0.3s ease-out",
                "slide-in": "slideIn 0.3s ease-out",
                pulse: "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
                "glow": "glow 2s ease-in-out infinite alternate",
            },
            keyframes: {
                fadeIn: {
                    "0%": { opacity: "0" },
                    "100%": { opacity: "1" },
                },
                slideUp: {
                    "0%": { opacity: "0", transform: "translateY(10px)" },
                    "100%": { opacity: "1", transform: "translateY(0)" },
                },
                slideIn: {
                    "0%": { opacity: "0", transform: "translateX(-10px)" },
                    "100%": { opacity: "1", transform: "translateX(0)" },
                },
                glow: {
                    "0%": { boxShadow: "0 0 5px rgba(160, 137, 104, 0.2)" },
                    "100%": { boxShadow: "0 0 20px rgba(160, 137, 104, 0.3)" },
                },
            },
            backdropBlur: {
                xs: "2px",
            },
        },
    },
    plugins: [],
};
