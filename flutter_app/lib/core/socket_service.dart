import 'dart:async';
import 'package:socket_io_client/socket_io_client.dart' as IO;

typedef EventCallback = void Function(dynamic data);

class SocketService {
  static final SocketService _instance = SocketService._internal();
  factory SocketService() => _instance;
  SocketService._internal();

  IO.Socket? _socket;
  String _serverUrl = 'http://localhost:5000';

  bool get isConnected => _socket?.connected ?? false;
  String get serverUrl => _serverUrl;

  Future<void> connect(String url) async {
    _serverUrl = url.trim();
    _socket?.disconnect();
    _socket?.dispose();

    final completer = Completer<void>();

    _socket = IO.io(
      _serverUrl,
      IO.OptionBuilder()
          .setTransports(['websocket', 'polling'])
          .enableReconnection()
          .setReconnectionAttempts(10)
          .setReconnectionDelay(2000)
          .build(),
    );

    _socket!.onConnect((_) {
      print('SocketIO: Verbunden mit $_serverUrl');
      if (!completer.isCompleted) completer.complete();
    });

    _socket!.onConnectError((e) {
      print('SocketIO: Verbindungsfehler: $e');
      if (!completer.isCompleted) completer.completeError(Exception('$e'));
    });

    _socket!.onDisconnect((_) => print('SocketIO: Verbindung getrennt'));

    return completer.future.timeout(
      const Duration(seconds: 8),
      onTimeout: () => throw TimeoutException('Server nicht erreichbar unter $_serverUrl'),
    );
  }

  void on(String event, EventCallback callback, {String namespace = '/'}) {
    _socket?.on(event, callback);
  }

  void off(String event) {
    _socket?.off(event);
  }

  void emit(String event, [dynamic data]) {
    _socket?.emit(event, data);
  }

  void disconnect() {
    _socket?.disconnect();
    _socket?.dispose();
    _socket = null;
  }
}
