"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Push-to-talk MediaRecorder hook.
 *
 * Phase 2: simple. Caller invokes `start()` (e.g. on pointerdown) and
 * `stop()` (on pointerup); `stop()` resolves with the recorded Blob.
 *
 * Output is `audio/webm;codecs=opus` — accepted by whisper.cpp + cloud
 * Whisper APIs without re-encoding.
 *
 * Phase 3 will replace this with continuous capture + Silero VAD + WS streaming.
 */
export interface VoiceRecorder {
    isRecording: boolean;
    isSupported: boolean;
    error: string | null;
    start: () => Promise<void>;
    stop: () => Promise<Blob | null>;
    cancel: () => void;
}

export function useVoiceRecorder(): VoiceRecorder {
    const [isRecording, setIsRecording] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const recorderRef = useRef<MediaRecorder | null>(null);
    const chunksRef = useRef<Blob[]>([]);
    const streamRef = useRef<MediaStream | null>(null);
    const stopResolveRef = useRef<((blob: Blob | null) => void) | null>(null);

    const isSupported =
        typeof window !== "undefined" &&
        typeof navigator !== "undefined" &&
        !!navigator.mediaDevices?.getUserMedia &&
        typeof window.MediaRecorder !== "undefined";

    const cleanup = useCallback(() => {
        recorderRef.current = null;
        chunksRef.current = [];
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
    }, []);

    const start = useCallback(async () => {
        if (!isSupported) {
            setError("Browser does not support audio recording");
            return;
        }
        if (recorderRef.current) return;
        setError(null);
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                },
            });
            streamRef.current = stream;
            const mimeCandidates = [
                "audio/webm;codecs=opus",
                "audio/webm",
                "audio/ogg;codecs=opus",
                "audio/mp4",
            ];
            const mime = mimeCandidates.find((m) => MediaRecorder.isTypeSupported(m)) || "";
            const recorder = mime
                ? new MediaRecorder(stream, { mimeType: mime })
                : new MediaRecorder(stream);

            chunksRef.current = [];
            recorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
            };
            recorder.onstop = () => {
                const type = recorder.mimeType || "audio/webm";
                const blob = chunksRef.current.length
                    ? new Blob(chunksRef.current, { type })
                    : null;
                stopResolveRef.current?.(blob);
                stopResolveRef.current = null;
                cleanup();
                setIsRecording(false);
            };
            recorder.onerror = (ev: Event) => {
                const msg = (ev as unknown as { error?: { message?: string } }).error?.message || "recorder error";
                setError(msg);
                stopResolveRef.current?.(null);
                stopResolveRef.current = null;
                cleanup();
                setIsRecording(false);
            };
            recorderRef.current = recorder;
            recorder.start();
            setIsRecording(true);
        } catch (err) {
            const msg = err instanceof Error ? err.message : "mic permission denied";
            setError(msg);
            cleanup();
            setIsRecording(false);
        }
    }, [cleanup, isSupported]);

    const stop = useCallback(async (): Promise<Blob | null> => {
        const rec = recorderRef.current;
        if (!rec || rec.state === "inactive") {
            cleanup();
            setIsRecording(false);
            return null;
        }
        return new Promise<Blob | null>((resolve) => {
            stopResolveRef.current = resolve;
            try {
                rec.stop();
            } catch {
                resolve(null);
                stopResolveRef.current = null;
                cleanup();
                setIsRecording(false);
            }
        });
    }, [cleanup]);

    const cancel = useCallback(() => {
        const rec = recorderRef.current;
        if (rec && rec.state !== "inactive") {
            try {
                rec.stop();
            } catch {
                // ignore
            }
        }
        // Drop the chunks so onstop yields null
        chunksRef.current = [];
        cleanup();
        setIsRecording(false);
    }, [cleanup]);

    // Safety: stop the stream if the component unmounts mid-recording
    useEffect(() => {
        return () => {
            cleanup();
        };
    }, [cleanup]);

    return { isRecording, isSupported, error, start, stop, cancel };
}
