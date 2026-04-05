/** WebSocket client for real-time agent updates. */

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

type MessageHandler = (message: any) => void;

class WSClient {
    private ws: WebSocket | null = null;
    private handlers: Map<string, Set<MessageHandler>> = new Map();
    private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    private pingTimer: ReturnType<typeof setInterval> | null = null;

    connect() {
        if (this.ws?.readyState === WebSocket.OPEN) return;

        try {
            this.ws = new WebSocket(`${WS_URL}/ws`);

            this.ws.onopen = () => {
                console.log("[WS] Connected");
                this.startPing();
                this.emit("connection", { status: "connected" });
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.emit(data.type, data);
                    this.emit("*", data); // Wildcard handler
                } catch {
                    console.warn("[WS] Invalid message:", event.data);
                }
            };

            this.ws.onclose = () => {
                console.log("[WS] Disconnected");
                this.stopPing();
                this.emit("connection", { status: "disconnected" });
                this.scheduleReconnect();
            };

            this.ws.onerror = (err) => {
                console.error("[WS] Error:", err);
            };
        } catch (err) {
            console.error("[WS] Connection failed:", err);
            this.scheduleReconnect();
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
        }
        this.handlers.get(type)!.add(handler);
        return () => this.off(type, handler);
    }

    off(type: string, handler: MessageHandler) {
        this.handlers.get(type)?.delete(handler);
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

    private scheduleReconnect() {
        if (this.reconnectTimer) return;
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            console.log("[WS] Reconnecting...");
            this.connect();
        }, 3000);
    }
}

export const wsClient = new WSClient();
