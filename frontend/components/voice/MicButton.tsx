"use client";

import { Mic, Loader2, Square } from "lucide-react";
import { useState } from "react";
import { voiceApi } from "@/lib/api";
import { useVoiceRecorder } from "@/lib/use-voice-recorder";

interface MicButtonProps {
    /** Called with the transcript when transcription succeeds. */
    onTranscript: (text: string) => void;
    /** STT provider override (matches `agent.voice_provider_stt`). */
    provider?: string | null;
    disabled?: boolean;
    /** Compact mode shrinks padding for inline toolbars. */
    compact?: boolean;
}

/**
 * Hold-to-talk mic. Starts recording on pointerdown, stops + transcribes on
 * pointerup. The transcript is handed to the parent via `onTranscript` —
 * the parent decides whether to drop it into the input box or send it
 * directly.
 */
export default function MicButton({ onTranscript, provider, disabled, compact }: MicButtonProps) {
    const recorder = useVoiceRecorder();
    const [transcribing, setTranscribing] = useState(false);

    if (!recorder.isSupported) return null;

    const busy = transcribing;
    const active = recorder.isRecording || busy;

    async function endRecording() {
        const blob = await recorder.stop();
        if (!blob || blob.size < 200) return; // ignore phantom-tap blobs
        setTranscribing(true);
        try {
            const result = await voiceApi.transcribe(blob, "en", provider || undefined);
            if (result.text) onTranscript(result.text);
        } catch (err) {
            console.error("transcribe failed:", err);
        } finally {
            setTranscribing(false);
        }
    }

    function handlePointerDown(e: React.PointerEvent) {
        if (disabled || busy) return;
        e.preventDefault();
        recorder.start();
    }

    function handlePointerUp(e: React.PointerEvent) {
        if (!recorder.isRecording) return;
        e.preventDefault();
        endRecording();
    }

    function handlePointerCancel() {
        if (recorder.isRecording) recorder.cancel();
    }

    const padding = compact ? "p-1.5" : "p-2";
    const iconSize = "w-4 h-4";
    const baseClasses = `${padding} rounded-lg transition-all`;
    const stateClasses = active
        ? "bg-rose-500 text-white animate-pulse"
        : disabled
            ? "bg-stone-100 text-stone-400 cursor-not-allowed"
            : "text-stone-400 hover:text-stone-600 hover:bg-stone-100";

    return (
        <button
            type="button"
            onPointerDown={handlePointerDown}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerCancel}
            onPointerLeave={handlePointerUp}
            disabled={disabled}
            title={recorder.isRecording ? "Release to send" : "Hold to record"}
            className={`${baseClasses} ${stateClasses}`}
        >
            {transcribing ? (
                <Loader2 className={`${iconSize} animate-spin`} />
            ) : recorder.isRecording ? (
                <Square className={iconSize} />
            ) : (
                <Mic className={iconSize} />
            )}
        </button>
    );
}
