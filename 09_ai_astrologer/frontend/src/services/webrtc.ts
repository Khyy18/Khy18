/** WebRTC abstraction layer */

export interface MediaTrack {
  id: string;
  kind: 'audio' | 'video';
  track: MediaStreamTrack;
}

export interface RTCSession {
  id: string;
  state: 'new' | 'connecting' | 'connected' | 'disconnected';
}

export interface RTCProvider {
  connect(url: string, token: string): Promise<void>;
  publishMicrophone(): Promise<MediaTrack>;
  subscribeTracks(onTrack: (track: MediaTrack) => void): void;
  disconnect(): void;
}

export interface MediaProviderConfig {
  type: 'webrtc' | 'websocket';
  url: string;
  token: string;
}

/**
 * Base class for WebRTC-style media providers.
 */
abstract class WebRTCManager implements RTCProvider {
  protected session: RTCSession = { id: '', state: 'new' };

  abstract connect(url: string, token: string): Promise<void>;
  abstract publishMicrophone(): Promise<MediaTrack>;
  abstract subscribeTracks(onTrack: (track: MediaTrack) => void): void;
  abstract disconnect(): void;
}

/**
 * SimpleWebRTC implementation using native RTCPeerConnection.
 * Can connect to a future SFU for audio streaming.
 */
export class SimpleWebRTC extends WebRTCManager {
  private pc: RTCPeerConnection | null = null;
  private localStream: MediaStream | null = null;
  private onTrackCallback: ((track: MediaTrack) => void) | null = null;

  async connect(url: string, _token: string): Promise<void> {
    this.pc = new RTCPeerConnection({
      iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
    });

    this.pc.ontrack = (event) => {
      if (this.onTrackCallback && event.track) {
        this.onTrackCallback({
          id: event.track.id,
          kind: event.track.kind as 'audio' | 'video',
          track: event.track,
        });
      }
    };

    this.session = { id: url, state: 'connecting' };

    // In a full implementation, signaling would happen here via WebSocket
    this.session.state = 'connected';
  }

  async publishMicrophone(): Promise<MediaTrack> {
    this.localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const audioTrack = this.localStream.getAudioTracks()[0];

    if (this.pc) {
      this.pc.addTrack(audioTrack, this.localStream);
    }

    return {
      id: audioTrack.id,
      kind: 'audio',
      track: audioTrack,
    };
  }

  subscribeTracks(onTrack: (track: MediaTrack) => void): void {
    this.onTrackCallback = onTrack;
  }

  disconnect(): void {
    if (this.localStream) {
      this.localStream.getTracks().forEach((t) => t.stop());
      this.localStream = null;
    }
    if (this.pc) {
      this.pc.close();
      this.pc = null;
    }
    this.session.state = 'disconnected';
  }
}

/**
 * WebSocketFallback implementation - sends audio over WebSocket.
 * Implements the same RTCProvider interface for uniform usage.
 */
export class WebSocketFallback extends WebRTCManager {
  private ws: WebSocket | null = null;
  private localStream: MediaStream | null = null;
  private onTrackCallback: ((track: MediaTrack) => void) | null = null;

  async connect(url: string, token: string): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(url);
        this.ws.binaryType = 'arraybuffer';
        this.session = { id: url, state: 'connecting' };

        this.ws.onopen = () => {
          // First-message auth pattern
          this.ws?.send(JSON.stringify({ type: 'auth', token }));
          this.session.state = 'connected';
          resolve();
        };

        this.ws.onmessage = (event: MessageEvent) => {
          if (event.data instanceof ArrayBuffer && this.onTrackCallback) {
            // Create a synthetic audio track from received data
            // In practice, audio is played directly; this is for interface compliance
            this.onTrackCallback({
              id: 'ws-audio-' + Date.now(),
              kind: 'audio',
              track: new MediaStreamTrack(), // placeholder
            });
          }
        };

        this.ws.onerror = () => {
          this.session.state = 'disconnected';
          reject(new Error('WebSocket connection failed'));
        };

        this.ws.onclose = () => {
          this.session.state = 'disconnected';
        };
      } catch (e) {
        reject(e);
      }
    });
  }

  async publishMicrophone(): Promise<MediaTrack> {
    this.localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const audioTrack = this.localStream.getAudioTracks()[0];

    // Audio would be captured via ScriptProcessorNode or AudioWorklet
    // and sent as binary frames over the WebSocket

    return {
      id: audioTrack.id,
      kind: 'audio',
      track: audioTrack,
    };
  }

  subscribeTracks(onTrack: (track: MediaTrack) => void): void {
    this.onTrackCallback = onTrack;
  }

  sendAudio(data: ArrayBuffer): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(data);
    }
  }

  disconnect(): void {
    if (this.localStream) {
      this.localStream.getTracks().forEach((t) => t.stop());
      this.localStream = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.session.state = 'disconnected';
  }
}

/**
 * Factory function that returns the appropriate media provider based on config.
 */
export function getMediaProvider(config: MediaProviderConfig): RTCProvider {
  switch (config.type) {
    case 'webrtc':
      return new SimpleWebRTC();
    case 'websocket':
    default:
      return new WebSocketFallback();
  }
}
