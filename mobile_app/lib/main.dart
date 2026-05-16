import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:hive_flutter/hive_flutter.dart';

import 'providers/auth_provider.dart';
import 'providers/theme_provider.dart';
import 'services/local_storage.dart';
import 'services/notification_service.dart';
import 'services/secure_storage_service.dart';
import 'services/sync_service.dart';
import 'theme/app_theme.dart';
import 'theme/page_transitions.dart';

import 'screens/login_screen.dart';
import 'screens/dashboard_screen.dart';
import 'screens/calculations_screen.dart';
import 'screens/data_screen.dart';
import 'screens/more_screen.dart';
import 'screens/salary_screen.dart';
import 'screens/vacation_screen.dart';
import 'screens/sick_screen.dart';
import 'screens/timesheet_screen.dart';
import 'screens/children_screen.dart';
import 'screens/journal_screen.dart';
import 'screens/kbk_screen.dart';
import 'screens/reminders_screen.dart';
import 'screens/ai_chat_screen.dart';
import 'screens/lock_screen.dart';
import 'screens/pin_setup_screen.dart';
import 'screens/onboarding_screen.dart';
import 'screens/profile_screen.dart';
import 'screens/document_scan_screen.dart';
import 'screens/compensation_screen.dart';
import 'screens/templates_screen.dart';
import 'screens/calendar_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Hive.initFlutter();
  await LocalStorage.init();
  final syncService = SyncService();
  await syncService.init();
  try {
    await NotificationService.init();
  } catch (e) {
    // App works without Firebase - it's optional
  }
  runApp(ProviderScope(
    overrides: [
      syncServiceProvider.overrideWithValue(syncService),
    ],
    child: const KindergartenApp(),
  ));
}

class KindergartenApp extends ConsumerWidget {
  const KindergartenApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authProvider);
    final currentThemeMode = ref.watch(themeProvider);

    final router = GoRouter(
      initialLocation: authState.isAuthenticated ? '/' : '/login',
      routes: [
        GoRoute(
          path: '/login',
          builder: (context, state) => const LoginScreen(),
        ),
        GoRoute(
          path: '/onboarding',
          builder: (context, state) => const OnboardingScreen(),
        ),
        GoRoute(
          path: '/',
          builder: (context, state) => const DashboardScreen(),
        ),
        GoRoute(
          path: '/calculations',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const CalculationsScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
        ),
        GoRoute(
          path: '/data',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const DataScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
        ),
        GoRoute(
          path: '/more',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const MoreScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
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
        GoRoute(
          path: '/pin_setup',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const PinSetupScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
        ),
        GoRoute(
          path: '/profile',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const ProfileScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
        ),
        GoRoute(
          path: '/compensation',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const CompensationScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
        ),
        GoRoute(
          path: '/templates',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const TemplatesScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
        ),
        GoRoute(
          path: '/calendar',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const CalendarScreen(),
            transitionDuration: const Duration(milliseconds: 300),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
              return SlideAndFadeTransition(
                  animation: animation, child: child);
            },
          ),
        ),
        GoRoute(
          path: '/lock',
          builder: (context, state) => LockScreen(onUnlocked: () {
            GoRouter.of(context).go('/');
          }),
        ),
        GoRoute(
          path: '/scan',
          pageBuilder: (context, state) => CustomTransitionPage(
            child: const DocumentScanScreen(),
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

    return AppLifecycleWrapper(
      child: MaterialApp.router(
        title: 'Помощник бухгалтера',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light,
        darkTheme: AppTheme.dark,
        themeMode: currentThemeMode,
        routerConfig: router,
      ),
    );
  }
}

/// Wrapper widget that handles app lifecycle for re-authentication
class AppLifecycleWrapper extends StatefulWidget {
  final Widget child;

  const AppLifecycleWrapper({super.key, required this.child});

  @override
  State<AppLifecycleWrapper> createState() => _AppLifecycleWrapperState();
}

class _AppLifecycleWrapperState extends State<AppLifecycleWrapper>
    with WidgetsBindingObserver {
  final SecureStorageService _storageService = SecureStorageService();
  bool _isLocked = false;
  bool _checkingLock = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _checkInitialLock();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<void> _checkInitialLock() async {
    final lockEnabled = await _storageService.isLockEnabled();
    final pin = await _storageService.getPin();
    if (lockEnabled && pin != null && pin.isNotEmpty) {
      final lastAuth = await _storageService.getLastAuthTime();
      if (lastAuth == null ||
          DateTime.now().difference(lastAuth).inMinutes >= 2) {
        setState(() {
          _isLocked = true;
          _checkingLock = false;
        });
        return;
      }
    }
    setState(() => _checkingLock = false);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _checkReauthNeeded();
    }
  }

  Future<void> _checkReauthNeeded() async {
    final lockEnabled = await _storageService.isLockEnabled();
    if (!lockEnabled) return;

    final pin = await _storageService.getPin();
    if (pin == null || pin.isEmpty) return;

    final lastAuth = await _storageService.getLastAuthTime();
    if (lastAuth == null ||
        DateTime.now().difference(lastAuth).inMinutes >= 2) {
      setState(() => _isLocked = true);
    }
  }

  void _onUnlocked() {
    setState(() => _isLocked = false);
  }

  @override
  Widget build(BuildContext context) {
    if (_checkingLock) {
      return const MaterialApp(
        home: Scaffold(body: SizedBox.shrink()),
      );
    }
    if (_isLocked) {
      return MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light,
        home: LockScreen(onUnlocked: _onUnlocked),
      );
    }
    return widget.child;
  }
}
