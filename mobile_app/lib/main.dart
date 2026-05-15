import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:hive_flutter/hive_flutter.dart';

import 'providers/auth_provider.dart';
import 'services/local_storage.dart';
import 'theme/app_theme.dart';

import 'screens/login_screen.dart';
import 'screens/dashboard_screen.dart';
import 'screens/salary_screen.dart';
import 'screens/vacation_screen.dart';
import 'screens/sick_screen.dart';
import 'screens/timesheet_screen.dart';
import 'screens/children_screen.dart';
import 'screens/journal_screen.dart';
import 'screens/kbk_screen.dart';
import 'screens/reminders_screen.dart';
import 'screens/payment_screen.dart';
import 'screens/ai_chat_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Hive.initFlutter();
  await LocalStorage.init();
  runApp(const ProviderScope(child: KindergartenApp()));
}

class KindergartenApp extends ConsumerWidget {
  const KindergartenApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authProvider);

    final router = GoRouter(
      initialLocation: authState.isAuthenticated ? '/' : '/login',
      routes: [
        GoRoute(
          path: '/login',
          builder: (context, state) => const LoginScreen(),
        ),
        GoRoute(
          path: '/',
          builder: (context, state) => const DashboardScreen(),
        ),
        GoRoute(
          path: '/salary',
          builder: (context, state) => const SalaryScreen(),
        ),
        GoRoute(
          path: '/vacation',
          builder: (context, state) => const VacationScreen(),
        ),
        GoRoute(
          path: '/sick',
          builder: (context, state) => const SickScreen(),
        ),
        GoRoute(
          path: '/timesheet',
          builder: (context, state) => const TimesheetScreen(),
        ),
        GoRoute(
          path: '/children',
          builder: (context, state) => const ChildrenScreen(),
        ),
        GoRoute(
          path: '/journal',
          builder: (context, state) => const JournalScreen(),
        ),
        GoRoute(
          path: '/kbk',
          builder: (context, state) => const KbkScreen(),
        ),
        GoRoute(
          path: '/reminders',
          builder: (context, state) => const RemindersScreen(),
        ),
        GoRoute(
          path: '/payment',
          builder: (context, state) => const PaymentScreen(),
        ),
        GoRoute(
          path: '/ai_chat',
          builder: (context, state) => const AiChatScreen(),
        ),
      ],
      redirect: (context, state) {
        final isLoggedIn = authState.isAuthenticated;
        final isLoginRoute = state.matchedLocation == '/login';

        if (!isLoggedIn && !isLoginRoute) return '/login';
        if (isLoggedIn && isLoginRoute) return '/';
        return null;
      },
    );

    return MaterialApp.router(
      title: 'Детский сад',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: ThemeMode.light,
      routerConfig: router,
    );
  }
}
