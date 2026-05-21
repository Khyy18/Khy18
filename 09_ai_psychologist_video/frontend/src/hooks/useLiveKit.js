import { useState, useEffect, useRef } from 'react';
import { Room, RoomEvent } from 'livekit-client';

/**
 * Хук для подключения к LiveKit комнате и получения удаленных треков (видео/аудио аватара).
 * Если token не предоставлен - хук не выполняет никаких действий (no-op).
 * @param {Object} options
 * @param {string|null} options.token - LiveKit access token
 * @param {string|null} options.serverUrl - LiveKit server URL (wss://...)
 * @returns {{ remoteVideoTrack, remoteAudioTrack, isConnected }}
 */
export function useLiveKit({ token, serverUrl } = {}) {
  const [remoteVideoTrack, setRemoteVideoTrack] = useState(null);
  const [remoteAudioTrack, setRemoteAudioTrack] = useState(null);
  const [isConnected, setIsConnected] = useState(false);

  const roomRef = useRef(null);

  useEffect(() => {
    // No-op если токен не предоставлен
    if (!token || !serverUrl) return;

    const room = new Room();
    roomRef.current = room;

    // Обработка подписки на удаленные треки
    function handleTrackSubscribed(track) {
      if (track.kind === 'video') {
        setRemoteVideoTrack(track);
      } else if (track.kind === 'audio') {
        setRemoteAudioTrack(track);
      }
    }

    function handleConnected() {
      setIsConnected(true);
    }

    function handleDisconnected() {
      setIsConnected(false);
      setRemoteVideoTrack(null);
      setRemoteAudioTrack(null);
    }

    room.on(RoomEvent.TrackSubscribed, handleTrackSubscribed);
    room.on(RoomEvent.Connected, handleConnected);
    room.on(RoomEvent.Disconnected, handleDisconnected);

    // Подключение к комнате
    room
      .connect(serverUrl, token)
      .catch((err) => {
        console.error('[useLiveKit] connection error:', err);
      });

    return () => {
      room.off(RoomEvent.TrackSubscribed, handleTrackSubscribed);
      room.off(RoomEvent.Connected, handleConnected);
      room.off(RoomEvent.Disconnected, handleDisconnected);
      room.disconnect();
      roomRef.current = null;
      setIsConnected(false);
      setRemoteVideoTrack(null);
      setRemoteAudioTrack(null);
    };
  }, [token, serverUrl]);

  return { remoteVideoTrack, remoteAudioTrack, isConnected };
}
