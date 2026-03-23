"use client";

/** Built-in avatar options for agents. Each is an emoji string stored as avatar_url. */
export const AGENT_AVATARS: { id: string; emoji: string; label: string }[] = [
    // Robots & Tech
    { id: "robot", emoji: "\u{1F916}", label: "Robot" },
    { id: "alien", emoji: "\u{1F47E}", label: "Alien" },
    { id: "satellite", emoji: "\u{1F6F0}\uFE0F", label: "Satellite" },
    { id: "gear", emoji: "\u2699\uFE0F", label: "Gear" },
    { id: "laptop", emoji: "\u{1F4BB}", label: "Laptop" },
    { id: "electric", emoji: "\u26A1", label: "Electric" },
    // People & Roles
    { id: "detective", emoji: "\u{1F575}\uFE0F", label: "Detective" },
    { id: "scientist", emoji: "\u{1F9D1}\u200D\u{1F52C}", label: "Scientist" },
    { id: "artist", emoji: "\u{1F9D1}\u200D\u{1F3A8}", label: "Artist" },
    { id: "teacher", emoji: "\u{1F9D1}\u200D\u{1F3EB}", label: "Teacher" },
    { id: "astronaut", emoji: "\u{1F9D1}\u200D\u{1F680}", label: "Astronaut" },
    { id: "technologist", emoji: "\u{1F9D1}\u200D\u{1F4BB}", label: "Technologist" },
    { id: "office", emoji: "\u{1F9D1}\u200D\u{1F4BC}", label: "Office Worker" },
    { id: "chef", emoji: "\u{1F9D1}\u200D\u{1F373}", label: "Chef" },
    // Animals
    { id: "fox", emoji: "\u{1F98A}", label: "Fox" },
    { id: "owl", emoji: "\u{1F989}", label: "Owl" },
    { id: "eagle", emoji: "\u{1F985}", label: "Eagle" },
    { id: "wolf", emoji: "\u{1F43A}", label: "Wolf" },
    { id: "octopus", emoji: "\u{1F419}", label: "Octopus" },
    { id: "butterfly", emoji: "\u{1F98B}", label: "Butterfly" },
    // Objects & Symbols
    { id: "brain", emoji: "\u{1F9E0}", label: "Brain" },
    { id: "crystal", emoji: "\u{1F52E}", label: "Crystal Ball" },
    { id: "shield", emoji: "\u{1F6E1}\uFE0F", label: "Shield" },
    { id: "target", emoji: "\u{1F3AF}", label: "Target" },
    { id: "rocket", emoji: "\u{1F680}", label: "Rocket" },
    { id: "fire", emoji: "\u{1F525}", label: "Fire" },
    { id: "star", emoji: "\u2B50", label: "Star" },
    { id: "diamond", emoji: "\u{1F48E}", label: "Diamond" },
    { id: "lightbulb", emoji: "\u{1F4A1}", label: "Lightbulb" },
    { id: "book", emoji: "\u{1F4DA}", label: "Books" },
];

const AVATAR_MAP = new Map(AGENT_AVATARS.map((a) => [a.id, a.emoji]));

/** Resolve an avatar_url to its display emoji, or null if not found. */
export function resolveAvatar(avatarUrl: string | null | undefined): string | null {
    if (!avatarUrl) return null;
    return AVATAR_MAP.get(avatarUrl) ?? null;
}

interface AgentAvatarProps {
    name: string;
    avatarUrl?: string | null;
    size?: "sm" | "md" | "lg";
    className?: string;
}

const SIZE_CLASSES = {
    sm: "w-8 h-8 text-base",
    md: "w-10 h-10 text-xl",
    lg: "w-14 h-14 text-3xl",
};

const LETTER_SIZE_CLASSES = {
    sm: "w-8 h-8 text-xs",
    md: "w-10 h-10 text-sm",
    lg: "w-14 h-14 text-lg",
};

export default function AgentAvatar({ name, avatarUrl, size = "md", className = "" }: AgentAvatarProps) {
    const emoji = resolveAvatar(avatarUrl);

    if (emoji) {
        return (
            <div
                className={`${SIZE_CLASSES[size]} rounded-lg bg-stone-100 dark:bg-stone-800 flex items-center justify-center shrink-0 ${className}`}
            >
                <span role="img" aria-label={avatarUrl ?? "avatar"}>
                    {emoji}
                </span>
            </div>
        );
    }

    // Fallback: letter initial with gradient
    return (
        <div
            className={`${LETTER_SIZE_CLASSES[size]} rounded-lg bg-gradient-to-br from-stone-500 to-stone-700 flex items-center justify-center text-white font-bold shadow-sm shrink-0 ${className}`}
        >
            {name?.charAt(0).toUpperCase() ?? "?"}
        </div>
    );
}

interface AvatarPickerProps {
    selected: string | null;
    onSelect: (avatarId: string | null) => void;
}

export function AvatarPicker({ selected, onSelect }: AvatarPickerProps) {
    return (
        <div className="grid grid-cols-10 gap-1.5">
            {AGENT_AVATARS.map((a) => (
                <button
                    key={a.id}
                    type="button"
                    onClick={() => onSelect(selected === a.id ? null : a.id)}
                    className={`w-9 h-9 rounded-lg flex items-center justify-center text-lg transition-all ${
                        selected === a.id
                            ? "bg-stone-200 dark:bg-stone-800/40 ring-2 ring-stone-600 scale-110"
                            : "bg-stone-50 dark:bg-stone-800 hover:bg-stone-100 dark:hover:bg-stone-700"
                    }`}
                    title={a.label}
                >
                    {a.emoji}
                </button>
            ))}
        </div>
    );
}
