import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import '../providers/auth_provider.dart';
import '../theme/app_colors.dart';
import '../widgets/floating_nav_bar.dart';
import '../widgets/stat_card.dart';

class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key});

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> {
  DateTime? _lastBackPress;

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);
    final role = authState.role;

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (didPop) return;
        final now = DateTime.now();
        if (_lastBackPress == null ||
            now.difference(_lastBackPress!) > const Duration(seconds: 2)) {
          _lastBackPress = now;
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Нажмите ещё раз для выхода'),
              duration: Duration(seconds: 2),
              behavior: SnackBarBehavior.floating,
            ),
          );
        } else {
          SystemNavigator.pop();
        }
      },
      child: Scaffold(
      body: Stack(
        children: [
          // Background gradient
          Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: Theme.of(context).brightness == Brightness.dark
                    ? [
                        Theme.of(context).scaffoldBackgroundColor,
                        const Color(0xFF1a1625),
                      ]
                    : [
                        const Color(0xFFFFFFFF),
                        const Color(0xFFF5F3FF),
                      ],
              ),
            ),
          ),
          // Main content
          SafeArea(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(24, 20, 24, 100),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Header with particle dots behind
                  Stack(
                    children: [
                      SizedBox(
                        width: double.infinity,
                        height: 60,
                        child: CustomPaint(
                          painter: _ParticleDotsPainter(),
                        ),
                      ),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Помощник бухгалтера',
                                style: GoogleFonts.spaceGrotesk(
                                  fontSize: 26,
                                  fontWeight: FontWeight.w700,
                                  letterSpacing: -1,
                                ),
                              ).animate().fadeIn(duration: 400.ms),
                              const SizedBox(height: 4),
                              Text(
                                _getDateString(),
                                style: Theme.of(context)
                                    .textTheme
                                    .bodyMedium
                                    ?.copyWith(
                                      color: AppColors.neutral,
                                    ),
                              ),
                            ],
                          ),
                          GestureDetector(
                            onTap: () => context.go('/profile'),
                            child: Container(
                              width: 42,
                              height: 42,
                              decoration: BoxDecoration(
                                color: AppColors.primary.withOpacity(0.1),
                                borderRadius: BorderRadius.circular(14),
                              ),
                              child: const Icon(
                                Icons.person_outline,
                                color: AppColors.primary,
                                size: 22,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                  const SizedBox(height: 28),
                  Row(
                    children: [
                      Expanded(
                        child: StatCard(
                          icon: Icons.people_outline,
                          value: '0',
                          label: 'Сотрудники',
                          animationDelay: 100,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: StatCard(
                          icon: Icons.child_care_outlined,
                          value: '0',
                          label: 'Дети',
                          iconColor: AppColors.success,
                          animationDelay: 200,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: StatCard(
                          icon: Icons.notifications_outlined,
                          value: '0',
                          label: 'Дедлайны',
                          iconColor: AppColors.warning,
                          animationDelay: 300,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  Text(
                    'Функции',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 16),
                  GridView.count(
                    crossAxisCount: 3,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    crossAxisSpacing: 12,
                    mainAxisSpacing: 12,
                    childAspectRatio: 0.9,
                    children: _buildMenuItems(context, role),
                  ),
                  const SizedBox(height: 20),
                  _AiCard(onTap: () => context.go('/ai_chat')),
                ],
              ),
            ),
          ),
          // Floating nav bar at bottom
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: FloatingNavBar(
              currentIndex: 0,
              onTap: (index) {
                switch (index) {
                  case 0:
                    break; // Already on dashboard
                  case 1:
                    context.go('/calculations');
                    break;
                  case 2:
                    context.go('/data');
                    break;
                  case 3:
                    context.go('/more');
                    break;
                }
              },
            ),
          ),
        ],
      ),
    ),
    );
  }

  List<Widget> _buildMenuItems(BuildContext context, UserRole role) {
    final allItems = <_MenuItem>[
      _MenuItem(
        icon: Icons.calculate_outlined,
        label: 'Зарплата',
        route: '/salary',
        roles: [UserRole.admin, UserRole.cashier],
      ),
      _MenuItem(
        icon: Icons.beach_access_outlined,
        label: 'Отпуск',
        route: '/vacation',
        roles: [UserRole.admin, UserRole.cashier, UserRole.director],
      ),
      _MenuItem(
        icon: Icons.local_hospital_outlined,
        label: 'Больничный',
        route: '/sick',
        roles: [UserRole.admin, UserRole.cashier, UserRole.director],
      ),
      _MenuItem(
        icon: Icons.calendar_month_outlined,
        label: 'Табель',
        route: '/timesheet',
        roles: [UserRole.admin, UserRole.director],
      ),
      _MenuItem(
        icon: Icons.child_care_outlined,
        label: 'Дети',
        route: '/children',
        roles: [UserRole.admin, UserRole.director],
      ),
      _MenuItem(
        icon: Icons.book_outlined,
        label: 'Журнал',
        route: '/journal',
        roles: [UserRole.admin, UserRole.cashier],
      ),
      _MenuItem(
        icon: Icons.document_scanner_outlined,
        label: 'Скан',
        route: '/scan',
        roles: [UserRole.admin, UserRole.cashier, UserRole.director],
      ),
      _MenuItem(
        icon: Icons.search,
        label: 'КБК',
        route: '/kbk',
        roles: [UserRole.admin, UserRole.cashier, UserRole.director],
      ),
      _MenuItem(
        icon: Icons.notifications_outlined,
        label: 'Дедлайны',
        route: '/reminders',
        roles: [UserRole.admin, UserRole.cashier, UserRole.director],
      ),
    ];

    final visibleItems =
        allItems.where((item) => item.roles.contains(role)).toList();

    return visibleItems.asMap().entries.map((entry) {
      final index = entry.key;
      final item = entry.value;
      return _FunctionCard(
        icon: item.icon,
        label: item.label,
        onTap: () => context.go(item.route),
        delay: 100 + (index * 50),
      );
    }).toList();
  }

  String _getDateString() {
    final now = DateTime.now();
    const months = [
      '',
      'января',
      'февраля',
      'марта',
      'апреля',
      'мая',
      'июня',
      'июля',
      'августа',
      'сентября',
      'октября',
      'ноября',
      'декабря',
    ];
    return '${now.day} ${months[now.month]} ${now.year}';
  }
}

/// Decorative particle dots painted behind the header
class _ParticleDotsPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFF6366F1).withOpacity(0.06)
      ..style = PaintingStyle.fill;

    // Fixed pseudo-random positions for decorative dots
    final dots = <Offset>[
      Offset(size.width * 0.85, size.height * 0.2),
      Offset(size.width * 0.72, size.height * 0.7),
      Offset(size.width * 0.92, size.height * 0.5),
      Offset(size.width * 0.60, size.height * 0.15),
      Offset(size.width * 0.78, size.height * 0.85),
      Offset(size.width * 0.95, size.height * 0.3),
      Offset(size.width * 0.65, size.height * 0.55),
      Offset(size.width * 0.88, size.height * 0.75),
      Offset(size.width * 0.55, size.height * 0.35),
      Offset(size.width * 0.70, size.height * 0.45),
      Offset(size.width * 0.82, size.height * 0.10),
      Offset(size.width * 0.58, size.height * 0.80),
      Offset(size.width * 0.90, size.height * 0.65),
    ];

    final sizes = <double>[
      3.0, 4.5, 2.5, 5.0, 3.5, 2.0, 4.0, 3.0, 5.5, 2.5, 4.0, 3.5, 2.0
    ];

    for (var i = 0; i < dots.length; i++) {
      canvas.drawCircle(dots[i], sizes[i], paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _FunctionCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final int delay;

  const _FunctionCard({
    required this.icon,
    required this.label,
    required this.onTap,
    this.delay = 0,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: () {
          HapticFeedback.selectionClick();
          onTap();
        },
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 32, color: AppColors.primary),
              const SizedBox(height: 10),
              Text(
                label,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.labelLarge?.copyWith(
                      fontSize: 12,
                    ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ),
    )
        .animate()
        .fadeIn(delay: Duration(milliseconds: delay), duration: 300.ms)
        .scale(begin: const Offset(0.9, 0.9), end: const Offset(1, 1));
  }
}

class _AiCard extends StatelessWidget {
  final VoidCallback onTap;

  const _AiCard({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(20),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: Colors.white,
              width: 2,
            ),
            gradient: const LinearGradient(
              colors: [
                Color(0xFF6366F1),
                Color(0xFF8B5CF6),
              ],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF6366F1).withOpacity(0.3),
                blurRadius: 16,
                offset: const Offset(0, 6),
              ),
            ],
          ),
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              borderRadius: BorderRadius.circular(20),
              onTap: onTap,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
                child: Row(
                  children: [
                    Container(
                      width: 52,
                      height: 52,
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.25),
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: const Icon(
                        Icons.auto_awesome,
                        color: Colors.white,
                        size: 28,
                      ),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'AI Ассистент',
                            style: GoogleFonts.spaceGrotesk(
                              fontSize: 20,
                              fontWeight: FontWeight.w700,
                              color: Colors.white,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            'Задайте вопрос по бухгалтерии',
                            style: GoogleFonts.manrope(
                              fontSize: 14,
                              color: Colors.white.withOpacity(0.9),
                            ),
                          ),
                        ],
                      ),
                    ),
                    Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.2),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: const Icon(
                        Icons.arrow_forward_ios,
                        color: Colors.white,
                        size: 16,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    )
        .animate()
        .fadeIn(delay: 600.ms, duration: 400.ms)
        .slideY(begin: 0.1, end: 0);
  }
}

class _MenuItem {
  final IconData icon;
  final String label;
  final String route;
  final List<UserRole> roles;

  const _MenuItem({
    required this.icon,
    required this.label,
    required this.route,
    required this.roles,
  });
}
