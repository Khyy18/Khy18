import 'dart:async';
import 'dart:convert';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:http/http.dart' as http;

import '../config.dart';

class SyncQueueEntry {
  final String id;
  final String endpoint;
  final String method;
  final Map<String, dynamic>? body;
  final String timestamp;
  final String status;
  final int retryCount;
  final int maxRetries;

  SyncQueueEntry({
    required this.id,
    required this.endpoint,
    required this.method,
    this.body,
    required this.timestamp,
    required this.status,
    this.retryCount = 0,
    this.maxRetries = 5,
  });

  Map<String, dynamic> toMap() => {
        'id': id,
        'endpoint': endpoint,
        'method': method,
        'body': body,
        'timestamp': timestamp,
        'status': status,
        'retryCount': retryCount,
        'maxRetries': maxRetries,
      };

  factory SyncQueueEntry.fromMap(Map<dynamic, dynamic> map) {
    return SyncQueueEntry(
      id: map['id'] as String,
      endpoint: map['endpoint'] as String,
      method: map['method'] as String,
      body: map['body'] != null
          ? Map<String, dynamic>.from(map['body'] as Map)
          : null,
      timestamp: map['timestamp'] as String,
      status: map['status'] as String,
      retryCount: (map['retryCount'] as int?) ?? 0,
      maxRetries: (map['maxRetries'] as int?) ?? 5,
    );
  }

  SyncQueueEntry copyWith({String? status, int? retryCount}) {
    return SyncQueueEntry(
      id: id,
      endpoint: endpoint,
      method: method,
      body: body,
      timestamp: timestamp,
      status: status ?? this.status,
      retryCount: retryCount ?? this.retryCount,
      maxRetries: maxRetries,
    );
  }
}

class SyncService {
  Box? _box;
  StreamSubscription? _connectivitySubscription;
  final _pendingCountController = StreamController<int>.broadcast();
  String? _authToken;
  bool _isProcessing = false;
  int _idCounter = 0;

  Stream<int> get pendingCountStream => _pendingCountController.stream;

  int get pendingCount {
    if (_box == null || !_box!.isOpen) return 0;
    final entries = _getEntries();
    return entries.where((e) => e.status == 'pending' || e.status == 'failed').length;
  }

  void setAuthToken(String? token) {
    _authToken = token;
  }

  Future<void> init() async {
    try {
      _box = await Hive.openBox('sync_queue');
    } catch (e) {
      // If Hive box fails to open, service degrades gracefully
      return;
    }
    _notifyPendingCount();
    _connectivitySubscription =
        Connectivity().onConnectivityChanged.listen((results) {
      final isConnected = results.any((r) => r != ConnectivityResult.none);
      if (isConnected) {
        processQueue();
      }
    });
  }

  String _generateId() {
    _idCounter++;
    final now = DateTime.now().microsecondsSinceEpoch;
    return '${now}_$_idCounter';
  }

  Future<void> addToQueue(String endpoint, String method,
      [Map<String, dynamic>? body]) async {
    if (_box == null || !_box!.isOpen) return;

    final entry = SyncQueueEntry(
      id: _generateId(),
      endpoint: endpoint,
      method: method,
      body: body,
      timestamp: DateTime.now().toIso8601String(),
      status: 'pending',
    );

    await _box!.put(entry.id, entry.toMap());
    _notifyPendingCount();
  }

  Future<void> processQueue() async {
    if (_box == null || !_box!.isOpen) return;
    if (_isProcessing) return;
    _isProcessing = true;

    try {
      final entries = _getEntries()
          .where((e) => e.status == 'pending' || e.status == 'failed')
          .toList();

      // Sort by timestamp for FIFO order
      entries.sort((a, b) => a.timestamp.compareTo(b.timestamp));

      for (final entry in entries) {
        // Update status to syncing
        await _box!.put(entry.id, entry.copyWith(status: 'syncing').toMap());
        _notifyPendingCount();

        try {
          final success = await _executeRequest(entry);
          if (success) {
            await _box!.delete(entry.id);
          } else {
            final newRetryCount = entry.retryCount + 1;
            if (newRetryCount >= entry.maxRetries) {
              // Move to dead_letter status - stop retrying
              await _box!.put(
                  entry.id,
                  entry.copyWith(status: 'dead_letter', retryCount: newRetryCount).toMap());
            } else {
              await _box!.put(
                  entry.id,
                  entry.copyWith(status: 'failed', retryCount: newRetryCount).toMap());
            }
          }
        } catch (e) {
          final newRetryCount = entry.retryCount + 1;
          if (newRetryCount >= entry.maxRetries) {
            await _box!.put(
                entry.id,
                entry.copyWith(status: 'dead_letter', retryCount: newRetryCount).toMap());
          } else {
            await _box!.put(
                entry.id,
                entry.copyWith(status: 'failed', retryCount: newRetryCount).toMap());
          }
        }
        _notifyPendingCount();
      }
    } finally {
      _isProcessing = false;
    }
  }

  Future<bool> _executeRequest(SyncQueueEntry entry) async {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}${entry.endpoint}');
    final headers = <String, String>{
      'Content-Type': 'application/json',
    };
    if (_authToken != null) {
      headers['Authorization'] = 'Bearer $_authToken';
    }

    http.Response response;

    try {
      switch (entry.method.toUpperCase()) {
        case 'POST':
          response = await http.post(
            uri,
            headers: headers,
            body: entry.body != null ? json.encode(entry.body) : null,
          );
          break;
        case 'PUT':
          response = await http.put(
            uri,
            headers: headers,
            body: entry.body != null ? json.encode(entry.body) : null,
          );
          break;
        case 'DELETE':
          response = await http.delete(uri, headers: headers);
          break;
        default:
          return false;
      }
    } catch (e) {
      return false;
    }

    // 409 Conflict - server wins, discard local change
    if (response.statusCode == 409) {
      return true; // Remove from queue (discarded)
    }

    // Success
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return true;
    }

    // Other errors - keep for retry
    return false;
  }

  List<SyncQueueEntry> _getEntries() {
    if (_box == null || !_box!.isOpen) return [];
    return _box!.values
        .map((v) => SyncQueueEntry.fromMap(v as Map<dynamic, dynamic>))
        .toList();
  }

  void _notifyPendingCount() {
    _pendingCountController.add(pendingCount);
  }

  Future<bool> isOnline() async {
    try {
      final results = await Connectivity().checkConnectivity();
      return results.any((r) => r != ConnectivityResult.none);
    } catch (e) {
      return true; // Assume online if check fails
    }
  }

  void dispose() {
    _connectivitySubscription?.cancel();
    _pendingCountController.close();
  }
}

final syncServiceProvider = Provider<SyncService>((ref) {
  return SyncService();
});
