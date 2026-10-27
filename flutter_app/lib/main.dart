import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'screens/startup_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setPreferredOrientations([DeviceOrientation.landscapeLeft, DeviceOrientation.landscapeRight]);
  SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
  runApp(const SchlagfertigApp());
}

class SchlagfertigApp extends StatelessWidget {
  const SchlagfertigApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Schlagfertig',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF05070D),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFFF5C518),
          surface: Color(0xFF0D1117),
        ),
        inputDecorationTheme: const InputDecorationTheme(
          border: OutlineInputBorder(),
          labelStyle: TextStyle(color: Colors.white54),
        ),
        useMaterial3: true,
      ),
      home: const StartupScreen(),
    );
  }
}
