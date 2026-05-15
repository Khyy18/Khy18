import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:hive_flutter/hive_flutter.dart';

import 'providers/auth_provider.dart';
import 'services/local_storage.dart';
import 'services/notification_service.dart';
import 'theme/app_theme.dart';
import 'theme/page_transitions.dart';

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
  try {
    await NotificationService.init();
  } catch (e) {
    // App works without Firebase - it's optional
  }
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
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const SalaryScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
        ),
        GoRoute(
          path: '/vacation',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const VacationScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
        ),
        GoRoute(
          path: '/sick',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const SickScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
        ),
        GoRoute(
          path: '/timesheet',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const TimesheetScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
        ),
        GoRoute(
          path: '/children',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const ChildrenScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
        ),
        GoRoute(
          path: '/journal',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const JournalScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
        ),
        GoRoute(
          path: '/kbk',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const KbkScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
        ),
        GoRoute(
          path: '/reminders',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const RemindersScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
        ),
        GoRoute(
          path: '/payment',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const PaymentScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
        ),
        GoRoute(
          path: '/ai_chat',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const AiChatScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
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
