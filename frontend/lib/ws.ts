/** WebSocket client for real-time agent updates.
 *
 * The backend only delivers event types a connection has subscribed to, so
 * `on(type, …)` subscribes automatically and every subscription is replayed
 * after a reconnect. "*" (all events) is allowed for owner/admin only.
 */

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

/** Events emitted locally by this client, never sent by the server. */
const LOCAL_EVENTS = new Set(["connection"]);

/** Close codes the backend uses for authentication problems. */
const AUTH_CLOSE_CODES = new Set([4001, 4003, 4401]);

const RECONNECT_MS = 3000;
const AUTH_RETRY_MS = 30000;

type MessageHandler = (message: any) => void;

function accessToken(): string | null {
    return typeof window !== "undefined" ? localStorage.getItem("sutra_access_token") : null;
}

class WSClient {
    private ws: WebSocket | null = null;
    private handlers: Map<string, Set<MessageHandler>> = new Map();
    private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    private pingTimer: ReturnType<typeof setInterval> | null = null;

    connect() {
        if (this.ws && this.ws.readyState <= WebSocket.OPEN) return;

        const token = accessToken();
        if (!token) {
            // Not logged in yet; try again later rather than opening a socket
            // the server will reject.
            this.scheduleReconnect(AUTH_RETRY_MS);
            return;
        }

        try {
            this.ws = new WebSocket(`${WS_URL}/ws?token=${encodeURIComponent(token)}`);

            this.ws.onopen = () => {
                console.log("[WS] Connected");
                this.startPing();
                this.resubscribe();
                this.emit("connection", { status: "connected" });
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === "error") console.warn("[WS]", data.message);
                    this.emit(data.type, data);
                    this.emit("*", data); // Wildcard handler
                } catch {
                    console.warn("[WS] Invalid message:", event.data);
                }
            };

            this.ws.onclose = (event) => {
                console.log("[WS] Disconnected", event.code);
                this.stopPing();
                this.emit("connection", { status: "disconnected" });
                this.scheduleReconnect(AUTH_CLOSE_CODES.has(event.code) ? AUTH_RETRY_MS : RECONNECT_MS);
            };

            this.ws.onerror = () => {
                console.warn("[WS] Connection error (check that the backend is running)");
            };
        } catch (err) {
            console.error("[WS] Connection failed:", err);
            this.scheduleReconnect(RECONNECT_MS);
        }
    }

    disconnect() {
        this.stopPing();
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        this.ws?.close();
        this.ws = null;
    }

    send(message: any) {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        }
    }

    on(type: string, handler: MessageHandler) {
        if (!this.handlers.has(type)) {
            this.handlers.set(type, new Set());
            if (!LOCAL_EVENTS.has(type)) this.send({ type: "subscribe", events: [type] });
        }
        this.handlers.get(type)!.add(handler);
        return () => this.off(type, handler);
    }

    off(type: string, handler: MessageHandler) {
        const set = this.handlers.get(type);
        if (!set) return;
        set.delete(handler);
        if (set.size === 0) {
            this.handlers.delete(type);
            if (!LOCAL_EVENTS.has(type)) this.send({ type: "unsubscribe", events: [type] });
        }
    }

    private resubscribe() {
        const events = [...this.handlers.keys()].filter((t) => !LOCAL_EVENTS.has(t));
        if (events.length) this.send({ type: "subscribe", events });
    }

    private emit(type: string, data: any) {
        this.handlers.get(type)?.forEach((handler) => handler(data));
    }

    private startPing() {
        this.pingTimer = setInterval(() => {
            this.send({ type: "ping" });
        }, 30000);
    }

    private stopPing() {
        if (this.pingTimer) {
            clearInterval(this.pingTimer);
            this.pingTimer = null;
        }
    }

    private scheduleReconnect(delay: number) {
        if (this.reconnectTimer) return;
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            console.log("[WS] Reconnecting...");
            this.connect();
        }, delay);
    }
}

export const wsClient = new WSClient();
