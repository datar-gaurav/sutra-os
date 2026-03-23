import type { AuthUser, TokenResponse } from "./api";

const ACCESS_TOKEN_KEY = "sutra_access_token";
const REFRESH_TOKEN_KEY = "sutra_refresh_token";
const USER_KEY = "sutra_user";

export const authStorage = {
    getToken: (): string | null =>
        typeof window !== "undefined" ? localStorage.getItem(ACCESS_TOKEN_KEY) : null,

    getRefreshToken: (): string | null =>
        typeof window !== "undefined" ? localStorage.getItem(REFRESH_TOKEN_KEY) : null,

    getUser: (): AuthUser | null => {
        if (typeof window === "undefined") return null;
        const raw = localStorage.getItem(USER_KEY);
        return raw ? (JSON.parse(raw) as AuthUser) : null;
    },

    save: (tokens: TokenResponse) => {
        localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
        localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
        localStorage.setItem(USER_KEY, JSON.stringify(tokens.user));
    },

    clear: () => {
        localStorage.removeItem(ACCESS_TOKEN_KEY);
        localStorage.removeItem(REFRESH_TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
    },

    isAuthenticated: (): boolean =>
        typeof window !== "undefined" && !!localStorage.getItem(ACCESS_TOKEN_KEY),
};
